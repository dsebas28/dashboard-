"""
Paso 3 (opcional) del pipeline: publica el almacen en PostgreSQL.

DuckDB sigue siendo el motor de transformacion: lee el Parquet y construye el
modelo en segundos (src/build_warehouse.py). Este script copia el resultado a
un servidor PostgreSQL, que aporta lo que un archivo analitico no tiene:
claves primarias y foraneas, restricciones CHECK, indices y acceso concurrente
de varios usuarios. Con DATABASE_URL definida, el tablero lee de PostgreSQL.

    set DATABASE_URL=postgresql://retail:retail@localhost:5432/retail   (Windows)
    export DATABASE_URL=postgresql://retail:retail@localhost:5432/retail (Linux/macOS)
    python src/publish_postgres.py

Toda la publicacion es una sola transaccion: si algo falla (una clave foranea,
un CHECK, un recuento que no cuadra), PostgreSQL conserva la version anterior.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import psycopg

RAIZ = Path(__file__).resolve().parents[1]
BD = RAIZ / "data" / "warehouse" / "retail.duckdb"
SQL_PG = RAIZ / "sql" / "postgres"

# Tablas del esquema en estrella, en orden de dependencia (las dimensiones antes
# que los hechos que las referencian). La columna linea_id de fact_lineas la
# genera PostgreSQL, por eso cada tabla declara las columnas que se copian.
TABLAS_CORE: dict[str, str] = {
    "dim_fecha": "CAST(fecha AS DATE) AS fecha, anio, mes, trimestre, CAST(inicio_mes AS DATE) AS inicio_mes, "
                 "anio_mes, dia_semana, nombre_dia, nombre_mes, es_fin_semana, es_temporada_alta",
    "dim_cliente": "cliente_id, pais, primera_compra, ultima_compra, dias_de_vida, identificado",
    "dim_producto": "sku, descripcion, tipo_linea, precio_mediano, primera_venta, ultima_venta",
    "dim_pais": "pais, region, es_mercado_local",
    "fact_facturas": "factura, cliente_id, fecha, fecha_hora, pais, lineas, skus_distintos, unidades, importe, es_devolucion",
    "fact_lineas": "factura, sku, cliente_id, fecha, fecha_hora, hora, pais, cantidad, precio_unitario, importe, "
                   "tipo_linea, naturaleza, precio_valido, computa_ingreso",
}

# Tipos DuckDB -> PostgreSQL para la capa mart (tablas de resultados sin restricciones).
TIPOS_MART = {
    "VARCHAR": "TEXT",
    "BIGINT": "BIGINT",
    "INTEGER": "INTEGER",
    "HUGEINT": "NUMERIC(38, 0)",
    "DOUBLE": "DOUBLE PRECISION",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
}


def nombres(columnas: str) -> str:
    """'CAST(fecha AS DATE) AS fecha, anio' -> 'fecha, anio' (nombre de destino de cada columna)."""
    return ", ".join(c.strip().split(" AS ")[-1].strip() for c in columnas.split(","))


def copiar(duck: duckdb.DuckDBPyConnection, pg: psycopg.Connection, origen: str, destino: str,
           select: str, columnas: str, tmp: Path) -> int:
    """Exporta una consulta de DuckDB a CSV y la carga en PostgreSQL con COPY."""
    archivo = tmp / f"{destino.replace('.', '_')}.csv"
    duck.execute(f"COPY (SELECT {select} FROM {origen}) TO '{archivo.as_posix()}' (FORMAT csv, HEADER false)")
    with pg.cursor() as cur, open(archivo, "rb") as f:
        with cur.copy(f"COPY {destino} ({columnas}) FROM STDIN WITH (FORMAT csv)") as copy:
            while bloque := f.read(1 << 20):
                copy.write(bloque)
        cur.execute(f"SELECT COUNT(*) FROM {destino}")
        return cur.fetchone()[0]


def tablas_mart(duck: duckdb.DuckDBPyConnection) -> dict[str, list[tuple[str, str]]]:
    filas = duck.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'mart'
        ORDER BY table_name, ordinal_position
    """).fetchall()
    tablas: dict[str, list[tuple[str, str]]] = {}
    for tabla, columna, tipo in filas:
        tablas.setdefault(tabla, []).append((columna, TIPOS_MART.get(tipo, "TEXT")))
    return tablas


def validar(duck: duckdb.DuckDBPyConnection, pg: psycopg.Connection) -> list[str]:
    """La copia debe cuadrar con el origen: mismas filas y misma facturacion."""
    fallos = []
    with pg.cursor() as cur:
        for tabla in TABLAS_CORE:
            esperado = duck.execute(f"SELECT COUNT(*) FROM core.{tabla}").fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM core.{tabla}")
            obtenido = cur.fetchone()[0]
            if esperado != obtenido:
                fallos.append(f"core.{tabla}: {esperado} filas en DuckDB, {obtenido} en PostgreSQL")
        esperado = round(duck.execute("SELECT SUM(importe) FROM core.fact_lineas").fetchone()[0], 2)
        cur.execute("SELECT SUM(importe) FROM core.fact_lineas")
        obtenido = float(cur.fetchone()[0])
        if abs(esperado - obtenido) > 0.01:
            fallos.append(f"facturacion total: {esperado} en DuckDB, {obtenido} en PostgreSQL")
    return fallos


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Define DATABASE_URL, por ejemplo postgresql://retail:retail@localhost:5432/retail")
        return 1
    if not BD.exists():
        print(f"No existe {BD}. Ejecuta antes: python src/build_warehouse.py")
        return 1

    inicio = time.perf_counter()
    duck = duckdb.connect(str(BD), read_only=True)

    with psycopg.connect(url) as pg, tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with pg.cursor() as cur:
            cur.execute((SQL_PG / "01_esquema.sql").read_text(encoding="utf-8"))

        for tabla, select in TABLAS_CORE.items():
            filas = copiar(duck, pg, f"core.{tabla}", f"core.{tabla}", select, nombres(select), tmp)
            print(f"  core.{tabla:<22} {filas:>10,} filas")

        for tabla, columnas in tablas_mart(duck).items():
            ddl = ", ".join(f'"{c}" {t}' for c, t in columnas)
            lista = ", ".join(f'"{c}"' for c, _ in columnas)
            with pg.cursor() as cur:
                cur.execute(f"CREATE TABLE mart.{tabla} ({ddl})")
            filas = copiar(duck, pg, f"mart.{tabla}", f"mart.{tabla}", lista, lista, tmp)
            print(f"  mart.{tabla:<22} {filas:>10,} filas")

        with pg.cursor() as cur:
            cur.execute((SQL_PG / "02_indices.sql").read_text(encoding="utf-8"))

        fallos = validar(duck, pg)
        if fallos:
            pg.rollback()
            print("\nLa publicacion NO se guardo. Fallos de validacion:")
            for f in fallos:
                print("  -", f)
            return 1
        # El bloque `with psycopg.connect(...)` hace COMMIT al salir sin errores.

    print(f"\nAlmacen publicado en PostgreSQL y validado en {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
