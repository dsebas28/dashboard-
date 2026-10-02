"""
Dashboard de analisis comercial - Online Retail II

Tablero sobre las transacciones reales de un minorista online britanico
(diciembre 2009 - diciembre 2011). Los datos viven en un almacen dimensional
construido por el pipeline de `src/`: en PostgreSQL si DATABASE_URL esta
definida, o en el archivo DuckDB si no. Esta capa solo consulta y dibuja.

Ejecutar con:  streamlit run app.py
"""

from __future__ import annotations

import calendar
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src import datos, graficos  # noqa: E402

st.set_page_config(
    page_title="Online Retail II · Dashboard comercial",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Estilo
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      .stApp {{ background: {graficos.SUPERFICIE}; }}
      .block-container {{ padding-top: 2.2rem; max-width: 1500px; }}
      h1, h2, h3 {{ color: {graficos.TINTA}; letter-spacing: -0.015em; }}

      /* Ficha de indicador */
      .ficha {{
          background: #ffffff;
          border: 1px solid {graficos.REJILLA};
          border-radius: 10px;
          padding: 1rem 1.15rem;
          height: 100%;
      }}
      .ficha .etiqueta {{
          color: {graficos.TINTA_SUAVE}; font-size: 0.82rem;
          text-transform: none; margin-bottom: 0.3rem;
      }}
      /* Cifras grandes con figuras proporcionales: las tabulares se ven sueltas */
      .ficha .valor {{
          color: {graficos.TINTA}; font-size: 1.85rem; font-weight: 600;
          line-height: 1.1; font-variant-numeric: proportional-nums;
      }}
      .ficha .apunte {{ color: {graficos.TINTA_TENUE}; font-size: 0.78rem; margin-top: 0.25rem; }}

      /* Cifra protagonista: una sola por vista */
      .heroe {{ font-size: 3.1rem; font-weight: 600; color: {graficos.TINTA};
                line-height: 1; font-variant-numeric: proportional-nums; }}

      div[data-testid="stMetricValue"] {{ font-size: 1.6rem; }}
      section[data-testid="stSidebar"] {{ background: #f6f5f2; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def ficha(columna, etiqueta: str, valor: str, apunte: str = "") -> None:
    columna.markdown(
        f"""<div class="ficha">
              <div class="etiqueta">{etiqueta}</div>
              <div class="valor">{valor}</div>
              <div class="apunte">{apunte}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def libras(valor) -> str:
    return graficos._libras(valor)


# -----------------------------------------------------------------------------
# Filtros
# -----------------------------------------------------------------------------
minimo, maximo = datos.rango_fechas()
paises_df = datos.catalogo_paises()

with st.sidebar:
    st.markdown("### Filtros")

    rango = st.date_input(
        "Periodo",
        value=(minimo, maximo),
        min_value=minimo,
        max_value=maximo,
        format="DD/MM/YYYY",
    )
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        desde, hasta = rango
    else:  # el control devuelve una sola fecha mientras se elige la segunda
        desde, hasta = minimo, maximo

    regiones = st.multiselect(
        "Region",
        options=sorted(paises_df["region"].unique()),
        default=[],
        placeholder="Todas las regiones",
    )
    disponibles = paises_df[paises_df["region"].isin(regiones)] if regiones else paises_df

    seleccion_paises = st.multiselect(
        "Pais",
        options=sorted(disponibles["pais"]),
        default=[],
        placeholder="Todos los paises",
    )
    paises_filtro = seleccion_paises or (sorted(disponibles["pais"]) if regiones else None)

    st.divider()
    st.caption(
        "**Fuente**  \nOnline Retail II · UCI Machine Learning Repository  \n"
        "Minorista online britanico de articulos de regalo  \n"
        f"{minimo:%d/%m/%Y} – {maximo:%d/%m/%Y}"
    )
    st.caption(
        "**Nota**  \nRFM, cohortes y clasificacion ABC se recalculan sobre el "
        "periodo seleccionado, no son cifras precalculadas."
    )
    st.caption(f"**Motor**  \n{datos.MOTOR}")

filtro, params = datos.construir_filtro(desde, hasta, paises_filtro)


def meses_incompletos() -> set[str]:
    """
    Meses que el filtro cubre solo en parte. Marcarlos evita el error de leer
    como caida lo que solo es un mes truncado: el dataset acaba el 9 de
    diciembre de 2011, asi que su ultimo mes siempre esta a un tercio.
    """
    parciales = set()
    if desde.day != 1:
        parciales.add(f"{desde.year}-{desde.month:02d}")
    ultimo_dia = calendar.monthrange(hasta.year, hasta.month)[1]
    if hasta.day != ultimo_dia:
        parciales.add(f"{hasta.year}-{hasta.month:02d}")
    return parciales


# -----------------------------------------------------------------------------
# Cabecera
# -----------------------------------------------------------------------------
k = datos.kpis(filtro, params)

st.markdown("## Analisis comercial · Online Retail II")
st.caption(
    f"Minorista online britanico de articulos de regalo · "
    f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y} · "
    f"{'Todos los mercados' if not paises_filtro else f'{len(paises_filtro)} mercados'}"
)

if k["facturacion"] == 0:
    st.warning("La seleccion actual no contiene ventas. Amplia el periodo o los mercados.")
    st.stop()

izq, der = st.columns([1, 3])
with izq:
    st.markdown(
        f"""<div class="ficha">
              <div class="etiqueta">Facturacion del periodo</div>
              <div class="heroe">{libras(k['facturacion'])}</div>
              <div class="apunte">{k['facturas']:,.0f} facturas · {k['unidades']:,.0f} unidades</div>
            </div>""",
        unsafe_allow_html=True,
    )
with der:
    c1, c2, c3, c4 = st.columns(4)
    ficha(c1, "Ticket medio", f"£{k['ticket_medio']:,.0f}", "por factura emitida")
    ficha(c2, "Clientes identificados", f"{k['clientes']:,.0f}", f"en {k['paises']:.0f} paises")
    ficha(c3, "Referencias vendidas", f"{k['skus']:,.0f}", "SKU distintos con venta")
    ficha(c4, "Tasa de devolucion", f"{k['tasa_devolucion']:.2f}%",
          f"{libras(k['devuelto'])} en notas de credito")

st.write("")

pestanas = st.tabs([
    "Resumen ejecutivo", "Clientes", "Productos", "Mercados", "Modelo y calidad del dato",
])

# =============================================================================
# 1 · RESUMEN EJECUTIVO
# =============================================================================
with pestanas[0]:
    mensual = datos.serie_mensual(filtro, params)
    parciales = meses_incompletos()

    st.markdown("#### Evolucion de la facturacion")
    if parciales:
        st.caption(
            "Los meses con cobertura parcial aparecen atenuados: no son una caida "
            f"de ventas, sino un mes incompleto ({', '.join(sorted(parciales))})."
        )
    st.plotly_chart(
        graficos.evolucion_mensual(mensual, parciales),
        width="stretch", config={"displayModeBar": False},
    )

    izq, der = st.columns(2)
    with izq:
        st.markdown("#### Composicion por region")
        st.plotly_chart(
            graficos.mezcla_regional(datos.mezcla_regional(filtro, params)),
            width="stretch", config={"displayModeBar": False},
        )
    with der:
        st.markdown("#### Tasa de devolucion mensual")
        st.plotly_chart(
            graficos.devoluciones_mensuales(mensual),
            width="stretch", config={"displayModeBar": False},
        )

    st.markdown("#### Cuando compra el negocio")
    st.caption(
        "Facturacion por dia de la semana y hora. Revela la ventana comercial "
        "real: un mayorista que factura en horario de oficina."
    )
    st.plotly_chart(
        graficos.mapa_calor_horario(datos.patron_horario(filtro, params)),
        width="stretch", config={"displayModeBar": False},
    )

    with st.expander("Ver los datos mensuales en tabla"):
        st.dataframe(
            mensual.assign(mes=mensual["anio_mes"]).drop(columns=["anio_mes"]),
            width="stretch", hide_index=True,
            column_config={
                "mes": "Mes",
                "facturacion": st.column_config.NumberColumn("Facturacion", format="£%.0f"),
                "devoluciones": st.column_config.NumberColumn("Devoluciones", format="£%.0f"),
                "facturas": st.column_config.NumberColumn("Facturas", format="%d"),
                "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
                "ticket_medio": st.column_config.NumberColumn("Ticket medio", format="£%.2f"),
                "media_movil_3m": st.column_config.NumberColumn("Media movil 3m", format="£%.0f"),
            },
        )

# =============================================================================
# 2 · CLIENTES
# =============================================================================
with pestanas[1]:
    tabla_rfm = datos.rfm(filtro, params)

    if tabla_rfm.empty:
        st.info("No hay clientes identificados en la seleccion actual.")
    else:
        resumen = (
            tabla_rfm.groupby("segmento")
            .agg(clientes=("cliente_id", "count"),
                 facturacion=("monetario", "sum"),
                 recencia_media=("recencia_dias", "mean"),
                 frecuencia_media=("frecuencia", "mean"),
                 gasto_medio=("monetario", "mean"))
            .reset_index()
        )
        resumen["pct_facturacion"] = 100 * resumen["facturacion"] / resumen["facturacion"].sum()
        resumen["pct_clientes"] = 100 * resumen["clientes"] / resumen["clientes"].sum()

        campeones = resumen[resumen["segmento"] == "Campeones"]
        pct_camp = float(campeones["pct_facturacion"].iloc[0]) if not campeones.empty else 0
        n_camp = int(campeones["clientes"].iloc[0]) if not campeones.empty else 0

        c1, c2, c3 = st.columns(3)
        ficha(c1, "Clientes analizados", f"{len(tabla_rfm):,}",
              "con identificador; las ventas anonimas quedan fuera del RFM")
        ficha(c2, "Peso de los Campeones", f"{pct_camp:.1f}%",
              f"{n_camp:,} clientes generan esa parte de la facturacion")
        ficha(c3, "Gasto medio por cliente", f"£{tabla_rfm['monetario'].mean():,.0f}",
              f"mediana £{tabla_rfm['monetario'].median():,.0f}")

        st.write("")
        izq, der = st.columns([1, 1])
        with izq:
            st.markdown("#### Facturacion por segmento RFM")
            st.caption("Segmentacion por recencia, frecuencia y valor monetario (quintiles).")
            st.plotly_chart(graficos.barras_segmentos(resumen),
                            width="stretch", config={"displayModeBar": False})
        with der:
            st.markdown("#### Concentracion de la facturacion")
            st.caption("Cuanto mas se aleja la curva de la diagonal, mas concentrado es el negocio.")
            st.plotly_chart(graficos.curva_pareto(tabla_rfm),
                            width="stretch", config={"displayModeBar": False})

        st.markdown("#### Mapa de clientes: recencia frente a valor")
        st.caption(
            "Cada punto es un cliente. El tono codifica cuantas veces ha comprado. "
            "El cuadrante inferior derecho reune a quien gastaba poco y ya no vuelve."
        )
        st.plotly_chart(graficos.dispersion_rfm(tabla_rfm),
                        width="stretch", config={"displayModeBar": False})

        st.markdown("#### Retencion por cohorte")
        st.caption(
            "Cada fila agrupa a los clientes segun el mes de su primera compra y "
            "sigue que porcentaje sigue activo en los meses siguientes."
        )
        st.plotly_chart(graficos.mapa_calor_cohortes(datos.cohortes(filtro, params)),
                        width="stretch", config={"displayModeBar": False})

        with st.expander("Ver el detalle de segmentos en tabla"):
            st.dataframe(
                resumen.sort_values("facturacion", ascending=False),
                width="stretch", hide_index=True,
                column_config={
                    "segmento": "Segmento",
                    "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
                    "facturacion": st.column_config.NumberColumn("Facturacion", format="£%.0f"),
                    "pct_facturacion": st.column_config.NumberColumn("% facturacion", format="%.1f%%"),
                    "pct_clientes": st.column_config.NumberColumn("% clientes", format="%.1f%%"),
                    "recencia_media": st.column_config.NumberColumn("Recencia media (dias)", format="%.0f"),
                    "frecuencia_media": st.column_config.NumberColumn("Compras medias", format="%.1f"),
                    "gasto_medio": st.column_config.NumberColumn("Gasto medio", format="£%.0f"),
                },
            )

# =============================================================================
# 3 · PRODUCTOS
# =============================================================================
with pestanas[2]:
    catalogo = datos.productos(filtro, params)

    if catalogo.empty:
        st.info("No hay ventas de producto en la seleccion actual.")
    else:
        clase_a = catalogo[catalogo["clase_abc"] == "A"]
        c1, c2, c3 = st.columns(3)
        ficha(c1, "Referencias con venta", f"{len(catalogo):,}", "SKU distintos en el periodo")
        ficha(c2, "Referencias de clase A", f"{len(clase_a):,}",
              f"el {100 * len(clase_a) / len(catalogo):.1f}% del catalogo concentra el 80% de la facturacion")
        ficha(c3, "Facturacion media por referencia",
              libras(catalogo["facturacion"].mean()),
              f"mediana {libras(catalogo['facturacion'].median())}")

        st.write("")
        izq, der = st.columns([3, 2])
        with izq:
            st.markdown("#### Las 15 referencias que mas facturan")
            st.plotly_chart(
                graficos.barras_horizontales(catalogo.head(15), "facturacion", "descripcion"),
                width="stretch", config={"displayModeBar": False},
            )
        with der:
            st.markdown("#### Clasificacion ABC")
            st.caption("Regla de gestion de inventario: A = 80% de la facturacion, B = hasta 95%, C = el resto.")
            st.plotly_chart(graficos.distribucion_abc(catalogo),
                            width="stretch", config={"displayModeBar": False})

        st.markdown("#### Productos con mas devoluciones")
        st.caption("Solo referencias con mas de £1.000 facturados, para que la tasa sea significativa.")
        problematicos = (catalogo[(catalogo["devuelto"] > 0) & (catalogo["facturacion"] > 1000)]
                         .nlargest(25, "devuelto"))
        if problematicos.empty:
            st.info("Ninguna referencia supera el umbral de devoluciones en esta seleccion.")
        else:
            st.dataframe(
                problematicos[["sku", "descripcion", "facturacion", "devuelto",
                               "tasa_devolucion_pct", "clase_abc"]],
                width="stretch", hide_index=True,
                column_config={
                    "sku": "SKU", "descripcion": "Descripcion",
                    "facturacion": st.column_config.NumberColumn("Facturacion", format="£%.0f"),
                    "devuelto": st.column_config.NumberColumn("Devuelto", format="£%.0f"),
                    "tasa_devolucion_pct": st.column_config.NumberColumn("Tasa", format="%.2f%%"),
                    "clase_abc": "Clase",
                },
            )

        st.markdown("#### Productos que se compran juntos")
        st.caption(
            "Analisis de cesta sobre el periodo completo (capa `mart.cesta`). "
            "El *lift* mide cuantas veces mas aparecen juntos de lo que explicaria el azar."
        )
        cesta = datos.tabla_mart("cesta").head(25)
        st.dataframe(
            cesta[["producto_a", "producto_b", "juntas", "soporte_pct", "confianza_pct", "lift"]],
            width="stretch", hide_index=True,
            column_config={
                "producto_a": "Producto A", "producto_b": "Producto B",
                "juntas": st.column_config.NumberColumn("Facturas juntas", format="%d"),
                "soporte_pct": st.column_config.NumberColumn("Soporte", format="%.2f%%"),
                "confianza_pct": st.column_config.NumberColumn("Confianza", format="%.1f%%"),
                "lift": st.column_config.NumberColumn("Lift", format="%.2f"),
            },
        )

# =============================================================================
# 4 · MERCADOS
# =============================================================================
with pestanas[3]:
    mercados = datos.mercados(filtro, params)

    if mercados.empty:
        st.info("No hay mercados con ventas en la seleccion actual.")
    else:
        local = mercados[mercados["pais"] == "United Kingdom"]["facturacion"].sum()
        exportacion = mercados["facturacion"].sum() - local

        c1, c2, c3 = st.columns(3)
        ficha(c1, "Mercados activos", f"{len(mercados):,}", "paises con facturacion en el periodo")
        ficha(c2, "Peso del mercado local", f"{100 * local / mercados['facturacion'].sum():.1f}%",
              f"{libras(local)} facturados en Reino Unido")
        ficha(c3, "Exportacion", libras(exportacion),
              f"repartida en {len(mercados[mercados['pais'] != 'United Kingdom']):,} paises")

        st.write("")
        st.markdown("#### Mercados por facturacion")
        st.caption(
            "Reino Unido se excluye del grafico porque concentra el grueso del negocio "
            "y aplastaria la escala del resto; su cifra esta arriba y en la tabla."
        )
        sin_local = mercados[mercados["pais"] != "United Kingdom"].head(15)
        if sin_local.empty:
            st.info("La seleccion no incluye mercados de exportacion.")
        else:
            st.plotly_chart(
                graficos.barras_horizontales(sin_local, "facturacion", "pais", alto=480),
                width="stretch", config={"displayModeBar": False},
            )

        st.markdown("#### Detalle por pais")
        st.dataframe(
            mercados[["pais", "region", "facturacion", "cuota_pct", "facturas",
                      "clientes", "ticket_medio", "tasa_devolucion_pct"]],
            width="stretch", hide_index=True,
            column_config={
                "pais": "Pais", "region": "Region",
                "facturacion": st.column_config.NumberColumn("Facturacion", format="£%.0f"),
                "cuota_pct": st.column_config.NumberColumn("Cuota", format="%.2f%%"),
                "facturas": st.column_config.NumberColumn("Facturas", format="%d"),
                "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
                "ticket_medio": st.column_config.NumberColumn("Ticket medio", format="£%.0f"),
                "tasa_devolucion_pct": st.column_config.NumberColumn("Devoluciones", format="%.2f%%"),
            },
        )

# =============================================================================
# 5 · MODELO Y CALIDAD DEL DATO
# =============================================================================
with pestanas[4]:
    st.markdown("#### De que datos se alimenta este tablero")
    st.markdown(
        "Fuente: **Online Retail II**, publicado por el *UCI Machine Learning "
        "Repository*. Son transacciones reales de un minorista online britanico "
        "dedicado a la venta de articulos de regalo, en su mayoria a clientes "
        "mayoristas, entre el 1 de diciembre de 2009 y el 9 de diciembre de 2011."
    )

    st.markdown("#### Que se descarto y por que")
    st.caption(
        "Ningun tablero deberia pedir que se confie en el a ciegas. Esta es la "
        "traza completa entre el fichero original y las cifras de arriba."
    )
    calidad = datos.tabla_mart("calidad_dato")
    st.dataframe(
        calidad[["etapa", "filas", "detalle"]],
        width="stretch", hide_index=True,
        column_config={
            "etapa": "Etapa",
            "filas": st.column_config.NumberColumn("Filas", format="%d"),
            "detalle": "Criterio aplicado",
        },
    )

    st.info(
        "**El hallazgo que mas afectaba a las cifras:** el libro de Excel original "
        "trae una hoja por ejercicio, pero sus rangos se solapan. Del 1 al 9 de "
        "diciembre de 2010 las mismas 22.523 lineas aparecen en las dos hojas, "
        "£377.488 contados dos veces. Cargar el fichero sin revisarlo infla la "
        "facturacion de ese mes en un 88%.",
        icon="🔍",
    )

    st.markdown("#### Modelo dimensional")
    st.caption(
        f"Esquema en estrella servido desde {datos.MOTOR}: un hecho al grano de linea de factura, "
        "cuatro dimensiones conformadas y una capa `mart` con los calculos publicados. "
        "DuckDB construye el almacen; PostgreSQL lo sirve con claves primarias y foraneas, "
        "restricciones CHECK e indices."
    )
    st.code(
        """stg  ── limpieza y tipado
 │    retail_crudo · descripcion_canonica
 │
core ── modelo dimensional (esquema estrella)
 │    fact_lineas ──┬── dim_fecha     (calendario continuo)
 │    fact_facturas ├── dim_cliente   (-1 = no identificado)
 │                  ├── dim_producto  (descripcion canonica, ABC)
 │                  └── dim_pais      (region, mercado local)
 │
mart ── capa publicada
      kpis · ventas_mensuales · rfm · cohortes · pareto_clientes
      productos · cesta · resumen_paises · calidad_dato""",
        language="text",
    )

    st.dataframe(
        datos.inventario_tablas(),
        width="stretch", hide_index=True,
        column_config={
            "esquema": "Esquema", "tabla": "Tabla",
            "filas": st.column_config.NumberColumn("Filas", format="%d"),
        },
    )

    st.markdown("#### El SQL del modelo")
    raiz = Path(__file__).parent / "sql"
    archivos = (sorted(raiz.glob("*.sql")) + sorted((raiz / "marts").glob("*.sql"))
                + sorted((raiz / "postgres").glob("*.sql")))
    elegido = st.selectbox(
        "Archivo", archivos,
        format_func=lambda p: p.relative_to(raiz).as_posix(),
    )
    st.code(elegido.read_text(encoding="utf-8"), language="sql")
