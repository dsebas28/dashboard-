# Guía del código

Recorrido por el código del tablero comercial de Online Retail II. Los fragmentos son copias literales del repositorio.

## Contenido

1. [El recorrido de los datos](#1-el-recorrido-de-los-datos)
2. [Ingesta: del Excel al Parquet](#2-ingesta-del-excel-al-parquet)
3. [Limpieza en SQL](#3-limpieza-en-sql)
4. [Construcción y validación del almacén](#4-construcción-y-validación-del-almacén)
5. [Publicación en PostgreSQL](#5-publicación-en-postgresql)
6. [Acceso a datos: un SQL para dos motores](#6-acceso-a-datos-un-sql-para-dos-motores)
7. [Gráficos](#7-gráficos)
8. [El tablero](#8-el-tablero)
9. [Pruebas](#9-pruebas)

## 1. El recorrido de los datos

```
src/ingest.py            Excel de UCI (45 MB, dos hojas) ──► data/raw/online_retail_II.parquet
src/build_warehouse.py   Parquet ──► sql/01..03 + sql/marts ──► data/warehouse/retail.duckdb
src/publish_postgres.py  retail.duckdb ──► sql/postgres ──► PostgreSQL        (opcional)
app.py                   lee core.* y mart.* de PostgreSQL o DuckDB ──► Streamlit
```

El SQL vive en archivos, no incrustado en Python: el modelo de datos se puede leer, revisar y versionar por sí mismo, y el propio tablero lo muestra en su última pestaña.

## 2. Ingesta: del Excel al Parquet

`src/ingest.py` descarga el ZIP del repositorio UCI, lee las dos hojas del libro y las une en un Parquet, guardando en la columna `source_sheet` de qué hoja viene cada fila. Esa columna es la que permite detectar después el solape entre hojas. Parquet es columnar y tipado: DuckDB lo lee en segundos, mientras que releer el Excel cada vez tardaría minutos.

## 3. Limpieza en SQL

`sql/01_staging.sql` encadena vistas, cada una con una regla documentada. La más importante es la primera:

```sql
CREATE OR REPLACE VIEW stg.sin_solape AS
SELECT *
FROM stg.retail_crudo
WHERE NOT (source_sheet = 'Year 2009-2010' AND InvoiceDate >= DATE '2010-12-01');
```

Las dos hojas del Excel se pisan del 1 al 9 de diciembre de 2010: sin esta regla, esas 22.523 líneas se contarían dos veces. Después vienen los duplicados exactos (`SELECT DISTINCT`), la descripción canónica de cada SKU (la variante más frecuente, con `ROW_NUMBER()`) y la clasificación de cada línea:

```sql
CASE
    WHEN t.Invoice LIKE 'C%'  THEN 'devolucion'
    WHEN t.Quantity < 0       THEN 'baja_inventario'
    ELSE 'venta'
END                                         AS naturaleza,
```

Nada se borra: se **etiqueta**. Así cada consulta decide qué incluir, y la tasa de devolución se puede calcular porque las devoluciones siguen ahí.

`sql/02_dimensiones.sql` y `sql/03_hechos.sql` construyen el esquema en estrella (ver [BASE-DE-DATOS.md](BASE-DE-DATOS.md)) y `sql/marts/` los cálculos publicados.

## 4. Construcción y validación del almacén

`src/build_warehouse.py` ejecuta los `.sql` en orden y, al terminar, comprueba invariantes que deben cumplirse siempre:

```python
check("integridad referencial producto",
      "SELECT COUNT(*) FROM core.fact_lineas f LEFT JOIN core.dim_producto d USING (sku) WHERE d.sku IS NULL", 0)
```

Si una comprobación falla, la construcción se detiene: es mejor enterarse ahí que en el tablero. Hay validaciones de integridad referencial, de nulos, de rango de fechas y del solape entre hojas.

## 5. Publicación en PostgreSQL

`src/publish_postgres.py` copia el almacén a PostgreSQL en una sola transacción. Cada tabla se exporta de DuckDB a CSV y se carga con `COPY`, el método de carga masiva de PostgreSQL:

```python
def copiar(duck: duckdb.DuckDBPyConnection, pg: psycopg.Connection, origen: str, destino: str,
           select: str, columnas: str, tmp: Path) -> int:
    """Exporta una consulta de DuckDB a CSV y la carga en PostgreSQL con COPY."""
    archivo = tmp / f"{destino.replace('.', '_')}.csv"
    duck.execute(f"COPY (SELECT {select} FROM {origen}) TO '{archivo.as_posix()}' (FORMAT csv, HEADER false)")
    with pg.cursor() as cur, open(archivo, "rb") as f:
        with cur.copy(f"COPY {destino} ({columnas}) FROM STDIN WITH (FORMAT csv)") as copy:
            while bloque := f.read(1 << 20):
                copy.write(bloque)
```

El orden importa: las dimensiones se cargan antes que los hechos, porque `fact_lineas` tiene claves foráneas hacia ellas. Al final, `validar()` compara el recuento de cada tabla y la facturación total con DuckDB; si no cuadran, `pg.rollback()` y PostgreSQL se queda como estaba. El millón de líneas se publica en unos dos minutos.

## 6. Acceso a datos: un SQL para dos motores

`src/datos.py` elige el motor según el entorno:

```python
DATABASE_URL = os.environ.get("DATABASE_URL")
MOTOR = "PostgreSQL" if DATABASE_URL else "DuckDB"
```

La conexión a PostgreSQL se abre en **modo de solo lectura** (`default_transaction_read_only=on`): el tablero no puede modificar el almacén aunque tuviera un error.

Las consultas están escritas en el SQL que entienden los dos motores. Por ejemplo, la recencia del RFM resta fechas en lugar de usar `DATE_DIFF` (que solo existe en DuckDB):

```python
(SELECT hoy FROM referencia) - MAX(fecha)                  AS recencia_dias,
```

Los filtros de la barra lateral nunca se concatenan al SQL: `construir_filtro` devuelve un fragmento con marcadores `?` y la lista de valores. Para PostgreSQL, `_consulta` traduce `?` al `%s` de psycopg y convierte `Decimal` y `date` a los tipos que esperan pandas y Plotly, para que el resto del código no note la diferencia.

Todas las funciones llevan `@st.cache_data`: Streamlit vuelve a ejecutar el script en cada interacción, y la caché evita repetir una consulta con los mismos filtros.

## 7. Gráficos

`src/graficos.py` concentra todas las figuras de Plotly para que el tablero se lea como un solo sistema:

- Una paleta categórica de orden fijo, validada para daltonismo; el color sigue a la entidad (la región), nunca a su posición en el ranking.
- Rampas de un solo tono para magnitudes continuas (mapas de calor).
- `_base()` aplica a todas las figuras la misma superficie, tipografía, rejilla y leyenda.

## 8. El tablero

`app.py` dibuja cinco pestañas: resumen ejecutivo, clientes, productos, mercados y modelo y calidad del dato. La barra lateral filtra por periodo, región y país, y RFM, cohortes y clasificación ABC se **recalculan** sobre el periodo elegido: un cliente "reciente" lo es respecto a la ventana que se mira. La barra lateral indica qué motor está en uso.

## 9. Pruebas

`tests/test_motores.py` ejecuta las ocho consultas del tablero contra DuckDB y contra PostgreSQL, con tres combinaciones de filtros, y compara los resultados columna a columna:

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Esta prueba encontró un error real: los quintiles del RFM (`NTILE`) se calculaban sin desempate, así que los clientes con el mismo valor en la frontera de un quintil caían en uno u otro de forma arbitraria. Ahora se desempata por `cliente_id` y el segmento de cada cliente es siempre el mismo. La única diferencia admitida entre motores es de un céntimo, por el redondeo de `DOUBLE` (DuckDB) frente a `NUMERIC` (PostgreSQL).
