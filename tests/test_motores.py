"""
Las consultas del tablero deben dar el mismo resultado en DuckDB y en PostgreSQL.

Ejecuta cada funcion de src/datos.py contra los dos motores, con varios filtros,
y compara los DataFrames columna a columna.

    set DATABASE_URL=postgresql://retail:retail@localhost:5432/retail
    python -m pytest tests -q

Requiere el almacen DuckDB construido y publicado en PostgreSQL
(src/build_warehouse.py y src/publish_postgres.py). Si falta alguno, se omite.
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL or not (RAIZ / "data" / "warehouse" / "retail.duckdb").exists(),
    reason="hace falta DATABASE_URL y el almacen DuckDB construido",
)

FILTROS = [
    (dt.date(2009, 12, 1), dt.date(2011, 12, 9), None),                       # todo el periodo
    (dt.date(2011, 1, 1), dt.date(2011, 6, 30), ["United Kingdom"]),          # un semestre, mercado local
    (dt.date(2010, 9, 1), dt.date(2010, 12, 31), ["France", "Germany", "EIRE"]),
]

# DuckDB guarda los importes como DOUBLE y PostgreSQL como NUMERIC exacto: un valor
# como 148,105 es 148,10499... en coma flotante y redondea a 148,10, mientras que
# PostgreSQL redondea a 148,11. Por eso se admite una diferencia de un centimo.
CENTIMO = 0.0101

CONSULTAS = ["kpis", "serie_mensual", "mezcla_regional", "patron_horario", "rfm", "cohortes", "productos", "mercados"]


def cargar(motor: str):
    """Importa src/datos.py apuntando a un motor concreto."""
    if motor == "postgres":
        os.environ["DATABASE_URL"] = URL
    else:
        os.environ.pop("DATABASE_URL", None)
    import datos

    return importlib.reload(datos)


def ordenar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if isinstance(df[col].dtype, pd.CategoricalDtype):
            df[col] = df[col].astype(str)
    claves = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype).startswith("datetime")]
    return df.sort_values(claves or list(df.columns)).reset_index(drop=True)


def resultados(motor: str) -> dict:
    datos = cargar(motor)
    salida = {}
    for desde, hasta, paises in FILTROS:
        filtro, params = datos.construir_filtro(desde, hasta, paises)
        for nombre in CONSULTAS:
            resultado = getattr(datos, nombre).__wrapped__(filtro, params)
            salida[(nombre, desde, tuple(paises or []))] = resultado
    datos.conexion.clear()
    return salida


@pytest.fixture(scope="module")
def ambos():
    duck = resultados("duckdb")
    pg = resultados("postgres")
    os.environ["DATABASE_URL"] = URL
    return duck, pg


@pytest.mark.parametrize("nombre", CONSULTAS)
def test_misma_respuesta_en_los_dos_motores(ambos, nombre):
    duck, pg = ambos
    for clave in (k for k in duck if k[0] == nombre):
        a, b = duck[clave], pg[clave]
        if isinstance(a, pd.Series):
            for campo in a.index:
                assert float(a[campo]) == pytest.approx(float(b[campo]), rel=1e-9, abs=CENTIMO), (clave, campo)
            continue
        assert len(a) == len(b), (clave, len(a), len(b))
        a, b = ordenar(a), ordenar(b)
        for col in a.columns:
            if pd.api.types.is_numeric_dtype(a[col]):
                assert a[col].astype(float).values == pytest.approx(b[col].astype(float).values, rel=1e-9, abs=CENTIMO), (clave, col)
            else:
                assert a[col].astype(str).tolist() == b[col].astype(str).tolist(), (clave, col)
