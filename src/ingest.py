"""
Paso 1 del pipeline: descarga y normaliza la fuente cruda.

Fuente: Online Retail II - UCI Machine Learning Repository (id 502).
Transacciones reales de un minorista online britanico registrado en el Reino
Unido, dedicado a la venta de articulos de regalo, en su mayoria a clientes
mayoristas. Periodo: 01/12/2009 - 09/12/2011.

El Excel original tarda ~4 minutos en parsearse, asi que lo convertimos una
sola vez a Parquet y el resto del pipeline trabaja sobre ese archivo.
"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"

ZIP_PATH = RAW / "online_retail_II.zip"
XLSX_PATH = RAW / "online_retail_II.xlsx"
PARQUET_PATH = RAW / "online_retail_II.parquet"

# Invoice y StockCode traen valores mixtos (numericos y alfanumericos como
# 'C489449' o 'gift_0001'). Si dejamos que pandas infiera, cada hoja adivina un
# tipo distinto y la concatenacion falla al escribir Parquet.
FORZAR_TEXTO = {"Invoice": str, "StockCode": str, "Description": str, "Country": str}


def descargar() -> None:
    if XLSX_PATH.exists():
        print(f"[ingest] Excel ya presente: {XLSX_PATH.name}")
        return

    RAW.mkdir(parents=True, exist_ok=True)
    print(f"[ingest] Descargando desde UCI ...")
    respuesta = requests.get(URL, timeout=300)
    respuesta.raise_for_status()
    ZIP_PATH.write_bytes(respuesta.content)

    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(RAW)
    print(f"[ingest] Descargado y extraido ({ZIP_PATH.stat().st_size / 1e6:.1f} MB)")


def a_parquet() -> pd.DataFrame:
    if PARQUET_PATH.exists():
        print(f"[ingest] Parquet ya presente, leyendo cache")
        return pd.read_parquet(PARQUET_PATH)

    inicio = time.time()
    libro = pd.ExcelFile(XLSX_PATH, engine="openpyxl")
    hojas = []

    for nombre in libro.sheet_names:
        hoja = libro.parse(nombre, dtype=FORZAR_TEXTO)
        # El nombre de la hoja es la unica pista del ejercicio fiscal al que
        # pertenece cada lote; lo conservamos para poder auditar el origen.
        hoja["source_sheet"] = nombre
        print(f"[ingest]   {nombre}: {len(hoja):,} filas ({time.time() - inicio:.0f}s)")
        hojas.append(hoja)

    crudo = pd.concat(hojas, ignore_index=True)
    crudo.columns = [c.strip().replace(" ", "_") for c in crudo.columns]
    crudo.to_parquet(PARQUET_PATH, index=False)

    print(f"[ingest] {len(crudo):,} filas -> {PARQUET_PATH.name} en {time.time() - inicio:.0f}s")
    return crudo


if __name__ == "__main__":
    descargar()
    df = a_parquet()
    print(f"\n[ingest] Columnas: {list(df.columns)}")
