"""Leitura de zips locais da BDGD com um File Geodatabase sintético minúsculo (sem rede, sem dado real)."""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
import yaml

from swsurv.bdgd import CAMADAS, achar_zip, camadas_do_zip, camadas_para_parquet, fonte_do_zip
from swsurv.config import ROOT, ZIPS_ENV, Config

ITEM = "0123456789abcdef0123456789abcdef"


def _gdb(destino: Path) -> Path:
    """Cria <destino>/amostra.gdb com EQSE e UNSEMT (UNREMT e EQRE ficam de fora de propósito)."""
    gdb = destino / "amostra.gdb"
    eqse = pd.DataFrame({"COD_ID": ["e1", "e2", "e3"], "DIST": pd.Series([404, 404, 404], dtype="int32"), "TUC": ["345", "210", "160"],
                         "DAT_IMO": ["15/06/2015", "01/01/1920", "0"], "UN_SE": ["u1", "u2", "u3"]})
    pyogrio.write_dataframe(eqse, gdb, layer="EQSE", driver="OpenFileGDB")
    pts = gpd.GeoDataFrame({"COD_ID": ["u1", "u2", "u3"], "TIP_UNID": ["32", "29", "22"]},
                           geometry=gpd.points_from_xy([-54.6, -54.7, -54.8], [-20.4, -20.5, -20.6]), crs=4674)
    pyogrio.write_dataframe(pts, gdb, layer="UNSEMT", driver="OpenFileGDB")
    return gdb


def _zip_da_gdb(gdb: Path, destino: Path) -> Path:
    """Zip no formato da ANEEL: uma pasta .gdb no topo do arquivo."""
    z = destino / f"bdgd_2025_{ITEM}.gdb.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(gdb.rglob("*")):
            if f.is_file():
                zf.write(f, f"{gdb.name}/{f.relative_to(gdb).as_posix()}")
    return z


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_zip_local_vira_o_mesmo_parquet_que_o_gdb_baixado(tmp_path):
    gdb = _gdb(tmp_path)
    z = _zip_da_gdb(gdb, tmp_path)
    assert camadas_do_zip(z) == [n for n, _ in pyogrio.list_layers(gdb)]

    do_zip = camadas_para_parquet(fonte_do_zip(z), tmp_path / "cache_zip" / "2025")
    do_gdb = camadas_para_parquet(gdb, tmp_path / "cache_gdb" / "2025")  # caminho do download do ArcGIS
    assert do_zip == do_gdb == {"UNSEMT": 3, "EQSE": 3}  # camadas que não existem no zip são puladas
    for camada in do_zip:
        a = pd.read_parquet(tmp_path / "cache_zip" / "2025" / f"{camada}.parquet")
        b = pd.read_parquet(tmp_path / "cache_gdb" / "2025" / f"{camada}.parquet")
        pd.testing.assert_frame_equal(a, b)

    eqse = pd.read_parquet(tmp_path / "cache_zip" / "2025" / "EQSE.parquet")
    assert eqse.TUC.tolist() == ["345", "210", "160"] and eqse.DIST.tolist() == [404, 404, 404]
    unsemt = pd.read_parquet(tmp_path / "cache_zip" / "2025" / "UNSEMT.parquet")
    assert "geometry" not in unsemt and unsemt.lon.round(1).tolist() == [-54.6, -54.7, -54.8]
    assert unsemt.lat.round(1).tolist() == [-20.4, -20.5, -20.6]
    assert not list((tmp_path / "cache_zip" / "2025").glob("*.tmp"))  # gravação atômica não deixa resto


def test_leitura_do_zip_nao_altera_o_zip_nem_extrai_nada(tmp_path):
    z = _zip_da_gdb(_gdb(tmp_path), tmp_path)
    antes, ls = _sha(z), sorted(p.name for p in tmp_path.iterdir())
    camadas_para_parquet(fonte_do_zip(z), tmp_path / "cache" / "2025", {"EQSE": False})
    assert _sha(z) == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([*ls, "cache"])  # só o cache novo apareceu
    assert [p.name for p in (tmp_path / "cache" / "2025").iterdir()] == ["EQSE.parquet"]  # só a camada pedida


def test_achar_zip_usa_o_nome_do_cache_compartilhado(tmp_path):
    z = tmp_path / f"bdgd_2025_{ITEM}.gdb.zip"
    z.write_bytes(b"")
    assert achar_zip(tmp_path, 2025, ITEM) == z
    with pytest.raises(FileNotFoundError, match="2024"):
        achar_zip(tmp_path, 2024, ITEM)


def test_camadas_padrao_sao_as_quatro_que_o_pipeline_le():
    assert CAMADAS == {"UNSEMT": True, "EQSE": False, "UNREMT": True, "EQRE": False}


def test_pasta_de_zips_argumento_vence_variavel_vence_yaml(monkeypatch, tmp_path):
    cfg = Config({"bdgd": {"zips_locais": str(tmp_path / "yaml")}})
    monkeypatch.delenv(ZIPS_ENV, raising=False)
    assert cfg.zips_locais() == tmp_path / "yaml"
    monkeypatch.setenv(ZIPS_ENV, str(tmp_path / "env"))
    assert cfg.zips_locais() == tmp_path / "env"
    assert cfg.zips_locais(tmp_path / "arg") == tmp_path / "arg"
    monkeypatch.setenv(ZIPS_ENV, "  ")
    assert Config({"bdgd": {}}).zips_locais() is None  # sem pasta: o script baixa do ArcGIS, como em MT


def test_script_00_le_zips_locais_e_retoma(tmp_path):
    """scripts/00_baixar_bdgd.py --zips: converte, pula o ano já pronto e refaz com --forcar."""
    zips = tmp_path / "zips"
    zips.mkdir()
    z = _zip_da_gdb(_gdb(tmp_path), zips)
    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text(yaml.safe_dump({"distribuidora": "EMS", "cod_aneel": 404,
                                        "paths": {"cache": str(tmp_path / "cache")},
                                        "bdgd": {"snapshots": {2025: ITEM}}}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SWSURV_")}
    env["PYTHONUTF8"] = "1"

    def roda(*extra):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "00_baixar_bdgd.py"), "--config", str(cfg_yaml),
                            "--zips", str(zips), *extra], check=False, capture_output=True, text=True, env=env, cwd=ROOT)
        assert r.returncode == 0, r.stderr
        return r.stdout

    antes = _sha(z)
    assert "2025 ok" in roda()
    marca = json.loads((tmp_path / "cache" / "2025" / "_origem.json").read_text(encoding="utf-8"))
    assert marca["zip"] == z.name and marca["item"] == ITEM and marca["camadas"] == {"UNSEMT": 3, "EQSE": 3}
    assert "já convertido" in roda()
    assert "2025 ok" in roda("--forcar")
    assert _sha(z) == antes
