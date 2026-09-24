"""
Capa de acceso a datos del dashboard.

El almacen tiene dos niveles y el dashboard usa los dos:

  - `core.*`   hechos y dimensiones. Se consultan EN VIVO con los filtros que
               el usuario mueve en la barra lateral. DuckDB agrega el millon de
               lineas en milisegundos, asi que no hace falta precalcular nada
               para que el tablero responda.
  - `mart.*`   capa publicada por `sql/marts/`. Se usa donde el calculo es
               global por definicion (analisis de cesta) o donde interesa
               mostrar el resultado del proceso batch (trazabilidad de limpieza).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

BD = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "retail.duckdb"


@st.cache_resource(show_spinner=False)
def conexion() -> duckdb.DuckDBPyConnection:
    if not BD.exists():
        st.error(
            "No se encuentra el almacen. Ejecuta primero:\n\n"
            "```\npython src/ingest.py\npython src/build_warehouse.py\n```"
        )
        st.stop()
    return duckdb.connect(str(BD), read_only=True)


def _consulta(sql: str, params: list | None = None) -> pd.DataFrame:
    return conexion().execute(sql, params or []).df()


# -----------------------------------------------------------------------------
# Construccion del filtro
# -----------------------------------------------------------------------------
def construir_filtro(desde, hasta, paises: list[str] | None) -> tuple[str, list]:
    """
    Devuelve el fragmento WHERE y sus parametros. Se pasa como argumento a cada
    consulta en lugar de interpolarlo, para no concatenar valores en el SQL.
    """
    condiciones = ["l.fecha BETWEEN ? AND ?"]
    params: list = [desde, hasta]

    if paises:
        marcadores = ", ".join("?" for _ in paises)
        condiciones.append(f"l.pais IN ({marcadores})")
        params.extend(paises)

    return " AND ".join(condiciones), params


# -----------------------------------------------------------------------------
# Catalogos para los controles de la barra lateral
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def rango_fechas() -> tuple[pd.Timestamp, pd.Timestamp]:
    fila = _consulta("SELECT MIN(fecha) AS d, MAX(fecha) AS h FROM core.fact_lineas").iloc[0]
    return fila["d"], fila["h"]


@st.cache_data(show_spinner=False)
def catalogo_paises() -> pd.DataFrame:
    return _consulta("SELECT pais, region FROM core.dim_pais ORDER BY region, pais")


# -----------------------------------------------------------------------------
# Resumen ejecutivo
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def kpis(filtro: str, params: list) -> pd.Series:
    sql = f"""
        WITH v AS (
            SELECT * FROM core.fact_lineas l
            WHERE {filtro} AND l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
        )
        SELECT
            COALESCE(SUM(importe) FILTER (WHERE naturaleza = 'venta'), 0)            AS facturacion,
            COALESCE(SUM(cantidad) FILTER (WHERE naturaleza = 'venta'), 0)           AS unidades,
            COUNT(DISTINCT factura) FILTER (WHERE naturaleza = 'venta')              AS facturas,
            COUNT(DISTINCT cliente_id) FILTER (WHERE cliente_id <> -1)               AS clientes,
            COUNT(DISTINCT sku)                                                      AS skus,
            COUNT(DISTINCT pais)                                                     AS paises,
            COALESCE(ABS(SUM(importe) FILTER (WHERE naturaleza = 'devolucion')), 0)  AS devuelto
        FROM v
    """
    fila = _consulta(sql, params).iloc[0]
    fila["ticket_medio"] = fila["facturacion"] / fila["facturas"] if fila["facturas"] else 0
    fila["tasa_devolucion"] = (
        100 * fila["devuelto"] / fila["facturacion"] if fila["facturacion"] else 0
    )
    return fila


@st.cache_data(show_spinner=False)
def serie_mensual(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        SELECT
            f.inicio_mes                                                             AS mes,
            f.anio_mes,
            ROUND(COALESCE(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 0), 2)           AS facturacion,
            ROUND(COALESCE(ABS(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion')), 0), 2) AS devoluciones,
            COUNT(DISTINCT l.factura)    FILTER (WHERE l.naturaleza = 'venta')        AS facturas,
            COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)            AS clientes
        FROM core.fact_lineas l
        JOIN core.dim_fecha f USING (fecha)
        WHERE {filtro} AND l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
        GROUP BY 1, 2
        ORDER BY 1
    """
    df = _consulta(sql, params)
    df["ticket_medio"] = (df["facturacion"] / df["facturas"].replace(0, pd.NA)).round(2)
    df["media_movil_3m"] = df["facturacion"].rolling(3, min_periods=1).mean().round(2)
    return df


@st.cache_data(show_spinner=False)
def mezcla_regional(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        SELECT
            f.inicio_mes    AS mes,
            p.region,
            ROUND(SUM(l.importe), 2) AS facturacion
        FROM core.fact_lineas l
        JOIN core.dim_fecha f USING (fecha)
        JOIN core.dim_pais  p USING (pais)
        WHERE {filtro} AND l.computa_ingreso AND l.naturaleza = 'venta'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return _consulta(sql, params)


@st.cache_data(show_spinner=False)
def patron_horario(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        SELECT
            f.dia_semana,
            f.nombre_dia,
            l.hora,
            ROUND(SUM(l.importe), 2) AS facturacion
        FROM core.fact_lineas l
        JOIN core.dim_fecha f USING (fecha)
        WHERE {filtro} AND l.computa_ingreso AND l.naturaleza = 'venta'
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
    """
    return _consulta(sql, params)


# -----------------------------------------------------------------------------
# Clientes: RFM, Pareto y cohortes recalculados sobre el periodo filtrado
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def rfm(filtro: str, params: list) -> pd.DataFrame:
    """
    Mismo algoritmo que `sql/marts/12_clientes.sql`, pero con la fecha de
    referencia y los quintiles recalculados dentro de la ventana elegida: un
    cliente 'reciente' lo es respecto al periodo que se esta mirando.
    """
    sql = f"""
        WITH v AS (
            SELECT l.* FROM core.fact_lineas l
            WHERE {filtro} AND l.computa_ingreso
              AND l.cliente_id <> -1 AND l.naturaleza = 'venta'
        ),
        referencia AS (SELECT MAX(fecha) + INTERVAL 1 DAY AS hoy FROM v),
        metricas AS (
            SELECT
                cliente_id,
                DATE_DIFF('day', MAX(fecha), (SELECT hoy FROM referencia)) AS recencia_dias,
                COUNT(DISTINCT factura)                                    AS frecuencia,
                ROUND(SUM(importe), 2)                                     AS monetario
            FROM v GROUP BY 1
        ),
        puntuado AS (
            SELECT *,
                6 - NTILE(5) OVER (ORDER BY recencia_dias) AS r,
                NTILE(5) OVER (ORDER BY frecuencia)        AS f,
                NTILE(5) OVER (ORDER BY monetario)         AS m
            FROM metricas
        )
        SELECT p.*, c.pais,
            ROUND(p.monetario / p.frecuencia, 2) AS ticket_medio,
            CASE
                WHEN p.r >= 4 AND p.f >= 4 AND p.m >= 4 THEN 'Campeones'
                WHEN p.r >= 4 AND p.f <= 2              THEN 'Nuevos prometedores'
                WHEN p.r >= 3 AND p.f >= 3              THEN 'Leales'
                WHEN p.r >= 3 AND p.m >= 4              THEN 'Gran gasto reciente'
                WHEN p.r <= 2 AND p.f >= 4              THEN 'No se pueden perder'
                WHEN p.r =  2 AND p.f >= 3              THEN 'En riesgo'
                WHEN p.r <= 2 AND p.f <= 2 AND p.m <= 2 THEN 'Hibernando'
                WHEN p.r <= 1                           THEN 'Perdidos'
                ELSE 'Atencion requerida'
            END AS segmento
        FROM puntuado p
        JOIN core.dim_cliente c USING (cliente_id)
    """
    return _consulta(sql, params)


@st.cache_data(show_spinner=False)
def cohortes(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        WITH v AS (
            SELECT l.* FROM core.fact_lineas l
            WHERE {filtro} AND l.computa_ingreso
              AND l.cliente_id <> -1 AND l.naturaleza = 'venta'
        ),
        primera AS (
            SELECT cliente_id, DATE_TRUNC('month', MIN(fecha)) AS cohorte FROM v GROUP BY 1
        ),
        actividad AS (
            SELECT DISTINCT v.cliente_id, p.cohorte, DATE_TRUNC('month', v.fecha) AS mes
            FROM v JOIN primera p USING (cliente_id)
        ),
        conteo AS (
            SELECT cohorte, DATE_DIFF('month', cohorte, mes) AS mes_indice,
                   COUNT(DISTINCT cliente_id) AS clientes
            FROM actividad GROUP BY 1, 2
        )
        SELECT
            strftime(c.cohorte, '%Y-%m') AS cohorte,
            c.mes_indice,
            c.clientes,
            t.clientes AS tamano,
            ROUND(100.0 * c.clientes / t.clientes, 1) AS retencion_pct
        FROM conteo c
        JOIN (SELECT cohorte, clientes FROM conteo WHERE mes_indice = 0) t USING (cohorte)
        ORDER BY 1, 2
    """
    return _consulta(sql, params)


# -----------------------------------------------------------------------------
# Producto y mercados
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def productos(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        WITH v AS (
            SELECT l.* FROM core.fact_lineas l
            WHERE {filtro} AND l.tipo_linea = 'producto' AND l.precio_valido
        ),
        agregado AS (
            SELECT
                sku,
                ROUND(COALESCE(SUM(importe) FILTER (WHERE naturaleza = 'venta'), 0), 2)  AS facturacion,
                COALESCE(SUM(cantidad) FILTER (WHERE naturaleza = 'venta'), 0)           AS unidades,
                COUNT(DISTINCT factura) FILTER (WHERE naturaleza = 'venta')              AS facturas,
                COUNT(DISTINCT cliente_id) FILTER (WHERE cliente_id <> -1)               AS clientes,
                ROUND(COALESCE(ABS(SUM(importe) FILTER (WHERE naturaleza = 'devolucion')), 0), 2) AS devuelto
            FROM v GROUP BY 1
        )
        SELECT
            a.*, d.descripcion, d.precio_mediano,
            ROUND(100.0 * a.devuelto / NULLIF(a.facturacion, 0), 2) AS tasa_devolucion_pct,
            ROUND(100.0 * SUM(a.facturacion) OVER (ORDER BY a.facturacion DESC)
                  / SUM(a.facturacion) OVER (), 2)                  AS pct_acumulado
        FROM agregado a
        JOIN core.dim_producto d USING (sku)
        WHERE a.facturacion > 0
        ORDER BY a.facturacion DESC
    """
    df = _consulta(sql, params)
    df["clase_abc"] = pd.cut(
        df["pct_acumulado"], bins=[-0.01, 80, 95, 100.01], labels=["A", "B", "C"]
    )
    return df


@st.cache_data(show_spinner=False)
def mercados(filtro: str, params: list) -> pd.DataFrame:
    sql = f"""
        SELECT
            l.pais, p.region,
            ROUND(COALESCE(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 0), 2) AS facturacion,
            COUNT(DISTINCT l.factura)    FILTER (WHERE l.naturaleza = 'venta')          AS facturas,
            COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)              AS clientes,
            ROUND(COALESCE(ABS(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion')), 0), 2) AS devuelto
        FROM core.fact_lineas l
        JOIN core.dim_pais p USING (pais)
        WHERE {filtro} AND l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
        GROUP BY 1, 2
        HAVING SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta') > 0
        ORDER BY facturacion DESC
    """
    df = _consulta(sql, params)
    total = df["facturacion"].sum()
    df["cuota_pct"] = (100 * df["facturacion"] / total).round(2) if total else 0
    df["ticket_medio"] = (df["facturacion"] / df["facturas"].replace(0, pd.NA)).round(2)
    df["tasa_devolucion_pct"] = (
        100 * df["devuelto"] / df["facturacion"].replace(0, pd.NA)
    ).round(2)
    return df


# -----------------------------------------------------------------------------
# Capa mart (calculo global, independiente del filtro)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def tabla_mart(nombre: str) -> pd.DataFrame:
    return _consulta(f"SELECT * FROM mart.{nombre}")


@st.cache_data(show_spinner=False)
def inventario_tablas() -> pd.DataFrame:
    return _consulta("""
        SELECT schema_name AS esquema, table_name AS tabla, estimated_size AS filas
        FROM duckdb_tables() ORDER BY 1, 2
    """)
