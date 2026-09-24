"""
Paso 2 del pipeline: construye el almacen DuckDB ejecutando los .sql en orden.

El objetivo de tener el SQL en archivos y no incrustado en Python es que el
modelo de datos se pueda leer, revisar y versionar por si mismo.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
PARQUET = RAIZ / "data" / "raw" / "online_retail_II.parquet"
BD = RAIZ / "data" / "warehouse" / "retail.duckdb"
SQL_DIR = RAIZ / "sql"


def archivos_sql() -> list[Path]:
    """Numerados primero (orden de dependencia), luego los marts."""
    base = sorted(p for p in SQL_DIR.glob("*.sql"))
    marts = sorted(p for p in (SQL_DIR / "marts").glob("*.sql"))
    return base + marts


def validar(con: duckdb.DuckDBPyConnection) -> list[str]:
    """
    Comprobaciones que deben cumplirse siempre. Si una falla, el almacen esta
    mal construido y es mejor enterarse aqui que en el dashboard.
    """
    fallos: list[str] = []

    def check(nombre: str, sql: str, esperado) -> None:
        obtenido = con.execute(sql).fetchone()[0]
        if obtenido != esperado:
            fallos.append(f"{nombre}: esperado {esperado}, obtenido {obtenido}")

    check("sin fechas fuera de rango",
          "SELECT COUNT(*) FROM core.fact_lineas WHERE fecha < '2009-12-01' OR fecha > '2011-12-09'", 0)
    check("sin importes nulos",
          "SELECT COUNT(*) FROM core.fact_lineas WHERE importe IS NULL", 0)
    check("integridad referencial producto",
          "SELECT COUNT(*) FROM core.fact_lineas f LEFT JOIN core.dim_producto d USING (sku) WHERE d.sku IS NULL", 0)
    check("integridad referencial cliente",
          "SELECT COUNT(*) FROM core.fact_lineas f LEFT JOIN core.dim_cliente d USING (cliente_id) WHERE d.cliente_id IS NULL", 0)
    check("integridad referencial fecha",
          "SELECT COUNT(*) FROM core.fact_lineas f LEFT JOIN core.dim_fecha d USING (fecha) WHERE d.fecha IS NULL", 0)
    check("clientes sin duplicar",
          "SELECT COUNT(*) - COUNT(DISTINCT cliente_id) FROM core.dim_cliente", 0)
    # Invariante del solape: la ventana duplicada (1-9 dic 2010) debe contener
    # exactamente una copia, la de la hoja 2010-2011 ya deduplicada.
    check("el solape entre hojas quedo eliminado", """
        SELECT (SELECT COUNT(*) FROM core.fact_lineas
                WHERE fecha BETWEEN '2010-12-01' AND '2010-12-09')
             - (SELECT COUNT(*) FROM (
                    SELECT DISTINCT Invoice, StockCode, Description, Quantity,
                                    InvoiceDate, Price, Customer_ID, Country
                    FROM stg.retail_crudo
                    WHERE source_sheet = 'Year 2010-2011' AND InvoiceDate < '2010-12-10'))
    """, 0)

    check("toda linea de ingreso tiene precio positivo",
          "SELECT COUNT(*) FROM core.fact_lineas WHERE computa_ingreso AND precio_unitario <= 0", 0)

    return fallos


def construir() -> None:
    if not PARQUET.exists():
        sys.exit("[build] Falta el Parquet. Ejecuta antes: python src/ingest.py")

    BD.parent.mkdir(parents=True, exist_ok=True)
    BD.unlink(missing_ok=True)  # reconstruccion limpia y reproducible

    con = duckdb.connect(str(BD))
    con.execute(f"SET VARIABLE ruta_parquet = '{PARQUET.as_posix()}'")

    inicio = time.time()
    for archivo in archivos_sql():
        t0 = time.time()
        con.execute(archivo.read_text(encoding="utf-8"))
        print(f"[build] {archivo.relative_to(RAIZ).as_posix():<34} {time.time() - t0:5.1f}s")

    print(f"\n[build] Almacen construido en {time.time() - inicio:.1f}s -> {BD.name}")

    tablas = con.execute("""
        SELECT schema_name AS esquema, table_name AS tabla, estimated_size AS filas
        FROM duckdb_tables() ORDER BY 1, 2
    """).df()
    print("\n" + tablas.to_string(index=False))

    print("\n[build] Validaciones:")
    fallos = validar(con)
    if fallos:
        for f in fallos:
            print(f"  FALLO  {f}")
        con.close()
        sys.exit(1)
    print("  Todas correctas.")

    print(f"\n[build] Tamano del archivo: {BD.stat().st_size / 1e6:.1f} MB")
    con.close()


if __name__ == "__main__":
    construir()
