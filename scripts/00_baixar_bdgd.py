"""Reconstrói do zero o cache por camada a partir da BDGD publicada pela ANEEL.

Para cada cadastro anual (IDs em configs/premissas.yaml) baixa o File Geodatabase do
ArcGIS Hub da ANEEL (~1 GB), grava em Parquet só as camadas usadas aqui
(<cache>/<ano>/<CAMADA>.parquet) e apaga o GDB. Adaptado do cache compartilhado dos
projetos irmãos (distribution-asset-risk / gd-hosting-capacity).

    python scripts/00_baixar_bdgd.py            # todos os anos
    python scripts/00_baixar_bdgd.py 2024 2025  # só alguns
"""
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import pyogrio
import requests

from swsurv.config import Config

ARCGIS = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"
CAMADAS = {"UNSEMT": True, "EQSE": False, "UNREMT": True, "EQRE": False}  # camada: lê geometria?

cfg = Config.load()
anos = [int(a) for a in sys.argv[1:]] or sorted(cfg["bdgd"]["snapshots"])


def baixa(item: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    z = dest / "bdgd.zip"
    for tentativa in range(4):
        try:
            with requests.get(ARCGIS.format(item=item), stream=True, timeout=3000) as r:
                r.raise_for_status()
                with open(z, "wb") as f:
                    f.writelines(r.iter_content(1 << 22))
            break
        except requests.RequestException:
            if tentativa == 3:
                raise
            time.sleep(2 ** (tentativa + 1))
    with zipfile.ZipFile(z) as zf:
        zf.extractall(dest)
    z.unlink()
    return next(p for p in dest.rglob("*.gdb") if p.is_dir())


for ano in anos:
    tmp = cfg.cache / "_raw" / str(ano)
    gdb = baixa(cfg["bdgd"]["snapshots"][ano], tmp)
    (cfg.cache / str(ano)).mkdir(parents=True, exist_ok=True)
    disponiveis = {n for n, _ in pyogrio.list_layers(gdb)}
    for camada, geom in CAMADAS.items():
        if camada not in disponiveis:
            continue
        df = pyogrio.read_dataframe(gdb, layer=camada, read_geometry=geom, use_arrow=True)
        if geom:
            g = df.geometry.to_crs(4326)
            df["lon"], df["lat"] = g.x, g.y
            df = pd.DataFrame(df.drop(columns="geometry"))
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].astype("string")
        df.to_parquet(cfg.cache / str(ano) / f"{camada}.parquet", index=False)
    shutil.rmtree(tmp, ignore_errors=True)
    print(ano, "ok", flush=True)
