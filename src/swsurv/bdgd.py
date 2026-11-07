"""BDGD (File Geodatabase da ANEEL) para o cache por camada: <cache>/<ano>/<CAMADA>.parquet.

Duas origens, o mesmo resultado:

* download do ArcGIS Hub, extração e leitura do .gdb (comportamento de MT, em scripts/00_baixar_bdgd.py);
* zip já baixado (``bdgd_<ano>_<item>.gdb.zip``), lido no próprio zip pelo GDAL (``/vsizip/``): só as camadas
  pedidas são abertas, nada é extraído nem alterado.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyogrio

CAMADAS = {"UNSEMT": True, "EQSE": False, "UNREMT": True, "EQRE": False}  # camada: lê geometria?


def achar_zip(pasta: Path, ano: int, item: str, padrao: str = "bdgd_{ano}_{item}.gdb.zip") -> Path:
    """Zip do cadastro `ano` (item do ArcGIS `item`) numa pasta de zips já baixados."""
    z = Path(pasta) / padrao.format(ano=ano, item=item)
    if not z.is_file():
        raise FileNotFoundError(f"zip da BDGD de {ano} não encontrado: {z}")
    return z


def fonte_do_zip(zip_path: Path) -> str:
    """Caminho virtual do GDAL para ler o .gdb de dentro do zip, sem extrair."""
    return "/vsizip/" + Path(zip_path).resolve().as_posix()


def camadas_do_zip(zip_path: Path) -> list[str]:
    return [n for n, _ in pyogrio.list_layers(fonte_do_zip(zip_path))]


def camadas_para_parquet(fonte: str | Path, destino: Path, camadas: dict[str, bool] | None = None) -> dict[str, int]:
    """Grava `<destino>/<CAMADA>.parquet` para cada camada pedida que existe em `fonte` (.gdb ou /vsizip/...).

    Camadas com geometria ganham as colunas lon/lat (WGS84) no lugar da geometria; colunas de texto viram
    `string`. A gravação é atômica (arquivo temporário e renomeação), então uma queda de energia no meio não
    deixa um Parquet pela metade. Devolve {camada: linhas}.
    """
    camadas = CAMADAS if camadas is None else camadas
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    disponiveis = {n for n, _ in pyogrio.list_layers(fonte)}
    linhas = {}
    for camada, geom in camadas.items():
        if camada not in disponiveis:
            continue
        df = pyogrio.read_dataframe(fonte, layer=camada, read_geometry=geom, use_arrow=True)
        if geom:
            g = df.geometry.to_crs(4326)
            df["lon"], df["lat"] = g.x, g.y
            df = pd.DataFrame(df.drop(columns="geometry"))
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].astype("string")
        final = destino / f"{camada}.parquet"
        tmp = destino / f"{camada}.parquet.tmp"
        df.to_parquet(tmp, index=False)
        os.replace(tmp, final)
        linhas[camada] = len(df)
    return linhas
