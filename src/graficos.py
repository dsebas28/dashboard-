"""
Construccion de las figuras del dashboard.

Todas las figuras salen de aqui para que el tablero se lea como un solo sistema:
una sola paleta, un solo tratamiento de ejes y de rejilla, y las mismas reglas
de etiquetado. La paleta categorica esta validada para daltonismo (separacion
CVD Delta E 9.1 en el peor par adyacente); el color se asigna por entidad y
nunca por posicion en el ranking, de modo que filtrar no repinta las series.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# Paleta
# -----------------------------------------------------------------------------
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SUAVE = "#52514e"
TINTA_TENUE = "#8a8983"
REJILLA = "#e8e7e3"

# Orden fijo de la paleta categorica (no se cicla ni se genera un noveno color).
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

# Rampa secuencial de un solo tono, claro -> oscuro. Para magnitud continua.
SECUENCIAL = [
    [0.00, "#eef5fd"], [0.15, "#cde2fb"], [0.30, "#9ec5f4"], [0.45, "#6da7ec"],
    [0.60, "#3987e5"], [0.75, "#256abf"], [0.90, "#184f95"], [1.00, "#0d366b"],
]

# Rampa ordinal (3 pasos discretos, ninguno mas claro que el paso 250).
ORDINAL_3 = ["#1c5cab", "#3987e5", "#86b6ef"]

ACENTO = CATEGORICA[0]

# El color sigue a la entidad: cada region conserva su tono aunque el filtro
# cambie cuantas regiones hay en pantalla.
COLOR_REGION = {
    "Reino Unido": CATEGORICA[0],
    "Resto de Europa": CATEGORICA[1],
    "America": CATEGORICA[2],
    "Asia-Pacifico": CATEGORICA[3],
    "Oriente Medio y Africa": CATEGORICA[4],
    "Sin clasificar": CATEGORICA[5],
}

ORDEN_REGIONES = list(COLOR_REGION)


def _base(fig: go.Figure, alto: int = 380, leyenda: bool = False) -> go.Figure:
    """Cromatismo comun: rejilla discreta, sin marco, tipografia en tinta."""
    fig.update_layout(
        height=alto,
        paper_bgcolor=SUPERFICIE,
        plot_bgcolor=SUPERFICIE,
        font=dict(family="Inter, Segoe UI, system-ui, sans-serif", size=13, color=TINTA_SUAVE),
        margin=dict(l=10, r=10, t=44, b=10),
        hoverlabel=dict(bgcolor="white", font_size=13, bordercolor=REJILLA),
        showlegend=leyenda,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(color=TINTA_SUAVE),
            title=dict(text=""),
        ),
        # text vacio explicito: sin el, el Plotly.js que incluye Streamlit pinta "undefined"
        title=dict(text="", font=dict(size=15, color=TINTA), x=0, xanchor="left", y=0.96),
    )
    # Rejilla de un paso respecto a la superficie, continua y fina.
    fig.update_xaxes(showgrid=False, showline=False, zeroline=False,
                     ticks="outside", ticklen=4, tickcolor=REJILLA,
                     tickfont=dict(color=TINTA_TENUE))
    fig.update_yaxes(showgrid=True, gridcolor=REJILLA, gridwidth=1,
                     showline=False, zeroline=False,
                     tickfont=dict(color=TINTA_TENUE))
    return fig


def _libras(valor: float) -> str:
    """Formato compacto en libras: la moneda del negocio es GBP."""
    if valor is None or pd.isna(valor):
        return "-"
    for corte, sufijo in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(valor) >= corte:
            return f"£{valor / corte:,.1f}{sufijo}"
    return f"£{valor:,.0f}"


# -----------------------------------------------------------------------------
# Evolucion
# -----------------------------------------------------------------------------
def evolucion_mensual(df: pd.DataFrame, meses_parciales: set[str] | None = None) -> go.Figure:
    """
    Columnas de facturacion con la media movil de tres meses encima.

    Ambas series comparten unidad y escala, asi que comparten eje: nunca se
    superponen dos escalas distintas en el mismo panel.
    """
    parciales = meses_parciales or set()
    # Los meses incompletos se marcan con opacidad reducida en lugar de con otro
    # color: no son otra categoria, son el mismo dato con menos cobertura.
    opacidades = [0.45 if m in parciales else 1.0 for m in df["anio_mes"]]

    fig = go.Figure()
    fig.add_bar(
        x=df["mes"], y=df["facturacion"], name="Facturacion",
        marker=dict(color=ACENTO, opacity=opacidades, cornerradius=4),
        hovertemplate="<b>%{x|%b %Y}</b><br>Facturacion: £%{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        x=df["mes"], y=df["media_movil_3m"], name="Media movil 3 meses",
        mode="lines", line=dict(color=CATEGORICA[1], width=2, shape="spline"),
        hovertemplate="<b>%{x|%b %Y}</b><br>Media 3m: £%{y:,.0f}<extra></extra>",
    )

    # Etiqueta selectiva: solo el mes punta, que es el que cuenta la historia.
    if not df.empty:
        punta = df.loc[df["facturacion"].idxmax()]
        fig.add_annotation(
            x=punta["mes"], y=punta["facturacion"], text=f"<b>{_libras(punta['facturacion'])}</b>",
            showarrow=False, yshift=14, font=dict(color=TINTA, size=12),
        )

    fig = _base(fig, alto=400, leyenda=True)
    fig.update_layout(bargap=0.55, hovermode="x unified")
    fig.update_yaxes(tickprefix="£", tickformat="~s")
    return fig


def mezcla_regional(df: pd.DataFrame) -> go.Figure:
    """Composicion mensual por region. Columnas apiladas con separacion."""
    tabla = df.pivot_table(index="mes", columns="region", values="facturacion",
                           aggfunc="sum", fill_value=0)

    fig = go.Figure()
    for region in ORDEN_REGIONES:
        if region not in tabla.columns or tabla[region].sum() == 0:
            continue
        fig.add_bar(
            x=tabla.index, y=tabla[region], name=region,
            # El hueco de 2px en color de superficie separa los segmentos; no se
            # dibuja borde alrededor de la marca.
            marker=dict(color=COLOR_REGION[region],
                        line=dict(width=1, color=SUPERFICIE)),
            hovertemplate=f"<b>{region}</b><br>%{{x|%b %Y}}: £%{{y:,.0f}}<extra></extra>",
        )

    fig = _base(fig, alto=380, leyenda=True)
    # Plotly invierte la leyenda cuando apila; la devolvemos al orden del stack.
    fig.update_layout(barmode="stack", bargap=0.45, legend_traceorder="normal")
    fig.update_yaxes(tickprefix="£", tickformat="~s")
    return fig


def mapa_calor_horario(df: pd.DataFrame) -> go.Figure:
    """Dia de la semana x hora. Magnitud continua -> rampa de un solo tono."""
    orden_dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    tabla = (df.pivot_table(index="nombre_dia", columns="hora", values="facturacion",
                            aggfunc="sum", fill_value=0)
               .reindex([d for d in orden_dias if d in df["nombre_dia"].unique()]))

    fig = go.Figure(go.Heatmap(
        z=tabla.values, x=tabla.columns, y=tabla.index,
        colorscale=SECUENCIAL, xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Facturacion", font=dict(size=12)),
                      tickprefix="£", tickformat="~s", thickness=12, outlinewidth=0),
        hovertemplate="<b>%{y} · %{x}:00</b><br>£%{z:,.0f}<extra></extra>",
    ))
    fig = _base(fig, alto=320)
    fig.update_xaxes(title=dict(text="Hora del dia", font=dict(size=12)), dtick=1)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


# -----------------------------------------------------------------------------
# Clientes
# -----------------------------------------------------------------------------
def barras_segmentos(df: pd.DataFrame) -> go.Figure:
    """
    Facturacion por segmento RFM. Una sola serie, asi que un solo tono y sin
    caja de leyenda: colorear nueve segmentos distintos seria asignar color a
    una categoria nominal sin que el color aporte informacion.
    """
    d = df.sort_values("facturacion")
    fig = go.Figure(go.Bar(
        x=d["facturacion"], y=d["segmento"], orientation="h",
        marker=dict(color=ACENTO, cornerradius=4),
        text=[_libras(v) for v in d["facturacion"]],
        textposition="outside", textfont=dict(color=TINTA_SUAVE, size=12),
        cliponaxis=False,
        customdata=d[["clientes", "pct_facturacion"]].values,
        hovertemplate="<b>%{y}</b><br>Facturacion: £%{x:,.0f}"
                      "<br>Clientes: %{customdata[0]:,}"
                      "<br>Peso: %{customdata[1]:.1f}%<extra></extra>",
    ))
    fig = _base(fig, alto=420)
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(showgrid=True, gridcolor=REJILLA, tickprefix="£",
                     tickformat="~s", range=[0, d["facturacion"].max() * 1.18])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=TINTA_SUAVE))
    return fig


def dispersion_rfm(df: pd.DataFrame) -> go.Figure:
    """
    Recencia frente a gasto, con la frecuencia codificada en la rampa secuencial.
    Escala logaritmica en el gasto: la distribucion es de cola larga y en lineal
    el 95% de los clientes se aplastaria contra el eje.
    """
    d = df[df["monetario"] > 0].copy()
    fig = go.Figure(go.Scattergl(
        x=d["recencia_dias"], y=d["monetario"], mode="markers",
        marker=dict(
            size=9, color=d["frecuencia"], colorscale=SECUENCIAL,
            cmin=1, cmax=min(d["frecuencia"].quantile(0.97), d["frecuencia"].max()),
            # Anillo en color de superficie: mantiene legible cada punto donde se solapan.
            line=dict(width=1, color=SUPERFICIE), opacity=0.85,
            colorbar=dict(title=dict(text="Compras", font=dict(size=12)),
                          thickness=12, outlinewidth=0),
        ),
        customdata=d[["cliente_id", "segmento", "frecuencia"]].values,
        hovertemplate="<b>Cliente %{customdata[0]}</b><br>%{customdata[1]}"
                      "<br>Recencia: %{x} dias<br>Gasto: £%{y:,.0f}"
                      "<br>Compras: %{customdata[2]}<extra></extra>",
    ))
    fig = _base(fig, alto=420)
    fig.update_xaxes(title=dict(text="Dias desde la ultima compra", font=dict(size=12)),
                     showgrid=True, gridcolor=REJILLA)
    fig.update_yaxes(title=dict(text="Gasto acumulado", font=dict(size=12)),
                     type="log", tickprefix="£")
    return fig


def curva_pareto(df: pd.DataFrame) -> go.Figure:
    """Concentracion de la facturacion: que % de clientes acumula que % del total."""
    d = df.sort_values("monetario", ascending=False).reset_index(drop=True)
    d["pct_clientes"] = 100 * (d.index + 1) / len(d)
    d["pct_facturacion"] = 100 * d["monetario"].cumsum() / d["monetario"].sum()

    fig = go.Figure()
    fig.add_scatter(
        x=d["pct_clientes"], y=d["pct_facturacion"], mode="lines", name="Facturacion acumulada",
        line=dict(color=ACENTO, width=2),
        fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
        hovertemplate="El %{x:.0f}% de los clientes<br>genera el %{y:.1f}% de la facturacion<extra></extra>",
    )
    # Referencia 80/20: la diagonal teorica contra la que se lee la curva real.
    fig.add_scatter(
        x=[0, 100], y=[0, 100], mode="lines", name="Reparto uniforme",
        line=dict(color=TINTA_TENUE, width=1), hoverinfo="skip",
    )

    if not d.empty:
        hito = d[d["pct_clientes"] <= 20]["pct_facturacion"].max()
        fig.add_annotation(
            x=20, y=hito, ax=70, ay=48,
            text=f"<b>20% de clientes → {hito:.0f}%</b><br>de la facturacion",
            showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=TINTA_TENUE,
            font=dict(color=TINTA, size=12), align="left",
        )

    # Dos trazas en pantalla: la leyenda es obligatoria como canal de identidad.
    fig = _base(fig, alto=380, leyenda=True)
    fig.update_xaxes(title=dict(text="% de clientes (ordenados por gasto)", font=dict(size=12)),
                     showgrid=True, gridcolor=REJILLA, range=[0, 100], ticksuffix="%")
    fig.update_yaxes(title=dict(text="% de facturacion acumulada", font=dict(size=12)),
                     range=[0, 100], ticksuffix="%")
    return fig


def mapa_calor_cohortes(df: pd.DataFrame, max_meses: int = 12) -> go.Figure:
    """Retencion por cohorte de alta. Magnitud continua -> rampa de un solo tono."""
    d = df[df["mes_indice"] <= max_meses]
    tabla = d.pivot_table(index="cohorte", columns="mes_indice",
                          values="retencion_pct", aggfunc="first")

    fig = go.Figure(go.Heatmap(
        z=tabla.values, x=tabla.columns, y=tabla.index,
        colorscale=SECUENCIAL, zmin=0, zmax=min(60, float(pd.DataFrame(tabla.values).max().max())),
        xgap=2, ygap=2,
        colorbar=dict(title=dict(text="% retenido", font=dict(size=12)),
                      ticksuffix="%", thickness=12, outlinewidth=0),
        hovertemplate="<b>Cohorte %{y}</b><br>Mes +%{x}: %{z:.1f}% activo<extra></extra>",
    ))
    fig = _base(fig, alto=430)
    fig.update_xaxes(title=dict(text="Meses desde la primera compra", font=dict(size=12)), dtick=1)
    # Sin type="category" Plotly interpreta "2009-12" como fecha y reescribe
    # la etiqueta a "Dec 2009", desalineando la lectura de la cohorte.
    fig.update_yaxes(showgrid=False, autorange="reversed",
                     type="category", tickfont=dict(size=11))
    return fig


# -----------------------------------------------------------------------------
# Producto y mercados
# -----------------------------------------------------------------------------
def barras_horizontales(df: pd.DataFrame, campo_valor: str, campo_etiqueta: str,
                        titulo_hover: str = "Facturacion", alto: int = 460) -> go.Figure:
    """Ranking generico. Una serie, un tono, valor etiquetado en la punta."""
    d = df.sort_values(campo_valor)
    etiquetas = [t if len(str(t)) <= 34 else str(t)[:33] + "…" for t in d[campo_etiqueta]]

    fig = go.Figure(go.Bar(
        x=d[campo_valor], y=etiquetas, orientation="h",
        marker=dict(color=ACENTO, cornerradius=4),
        text=[_libras(v) for v in d[campo_valor]],
        textposition="outside", textfont=dict(color=TINTA_SUAVE, size=12),
        cliponaxis=False,
        hovertemplate=f"<b>%{{y}}</b><br>{titulo_hover}: £%{{x:,.0f}}<extra></extra>",
    ))
    fig = _base(fig, alto=alto)
    fig.update_layout(bargap=0.4)
    fig.update_xaxes(showgrid=True, gridcolor=REJILLA, tickprefix="£", tickformat="~s",
                     range=[0, d[campo_valor].max() * 1.20])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=TINTA_SUAVE, size=12))
    return fig


def distribucion_abc(df: pd.DataFrame) -> go.Figure:
    """
    Clasificacion ABC de inventario. A/B/C es una escala ORDENADA, no nominal,
    asi que recibe una rampa ordinal de un tono y no colores categoricos.
    """
    resumen = (df.groupby("clase_abc", observed=True)
                 .agg(referencias=("sku", "count"), facturacion=("facturacion", "sum"))
                 .reindex(["A", "B", "C"]).fillna(0).reset_index())
    total_ref = resumen["referencias"].sum()
    total_fac = resumen["facturacion"].sum()

    # En horizontal con solo tres categorias la marca no llena la banda y la
    # etiqueta cabe entera al final de la barra, sin quedar suspendida encima.
    resumen = resumen.iloc[::-1]

    fig = go.Figure()
    fig.add_bar(
        x=resumen["facturacion"], y=["Clase " + c for c in resumen["clase_abc"]],
        orientation="h",
        marker=dict(color=list(reversed(ORDINAL_3)), cornerradius=4),
        text=[f"{_libras(v)}  ·  {n:,.0f} refs ({100 * n / total_ref:.0f}%)"
              for v, n in zip(resumen["facturacion"], resumen["referencias"])],
        textposition="outside", textfont=dict(color=TINTA_SUAVE, size=12),
        cliponaxis=False,
        customdata=resumen[["referencias"]].values,
        hovertemplate="<b>%{y}</b><br>Facturacion: £%{x:,.0f}"
                      "<br>Referencias: %{customdata[0]:,}<extra></extra>",
    )
    fig = _base(fig, alto=360)
    fig.update_layout(bargap=0.6)
    fig.update_xaxes(title=dict(text="A concentra el 80% de la facturacion", font=dict(size=12)),
                     showgrid=True, gridcolor=REJILLA, tickprefix="£", tickformat="~s",
                     range=[0, total_fac * 1.05] if total_fac else None)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=TINTA_SUAVE, size=13))
    return fig


def devoluciones_mensuales(df: pd.DataFrame) -> go.Figure:
    """Tasa de devolucion mensual sobre facturacion bruta."""
    d = df.copy()
    d["tasa"] = (100 * d["devoluciones"] / d["facturacion"].replace(0, pd.NA)).round(2)

    fig = go.Figure(go.Bar(
        x=d["mes"], y=d["tasa"],
        marker=dict(color=CATEGORICA[1], cornerradius=4),
        customdata=d[["devoluciones"]].values,
        hovertemplate="<b>%{x|%b %Y}</b><br>Tasa: %{y:.2f}%"
                      "<br>Importe devuelto: £%{customdata[0]:,.0f}<extra></extra>",
    ))
    if d["tasa"].notna().any():
        media = d["tasa"].mean()
        fig.add_hline(y=media, line=dict(color=TINTA_TENUE, width=1),
                      annotation_text=f"Media del periodo: {media:.2f}%",
                      annotation_position="top left",
                      annotation_font=dict(color=TINTA_SUAVE, size=12))
    fig = _base(fig, alto=330)
    fig.update_layout(bargap=0.45)
    fig.update_yaxes(ticksuffix="%")
    return fig
