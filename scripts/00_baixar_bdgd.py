"""Reconstrói do zero o cache por camada a partir da BDGD publicada pela ANEEL.

Para cada cadastro anual (IDs em configs/premissas.yaml) baixa o File Geodatabase do
ArcGIS Hub da ANEEL (~1 GB), grava em Parquet só as camadas usadas aqui
(<cache>/<ano>/<CAMADA>.parquet) e apaga o GDB. Adaptado do cache compartilhado dos
projetos irmãos (distribution-asset-risk / gd-hosting-capacity).

    python scripts/00_baixar_bdgd.py            # todos os anos
    python scripts/00_baixar_bdgd.py 2024 2025  # só alguns

Outra distribuidora: --config configs/premissas_ems.yaml (ou SWSURV_CONFIG).

Zips já baixados (por exemplo o cache compartilhado da Energisa MS): --zips PASTA (ou SWSURV_BDGD_ZIPS, ou
bdgd.zips_locais no YAML) lê o `bdgd_<ano>_<item>.gdb.zip` de cada ano direto do zip, só nas camadas necessárias,
sem baixar, sem extrair e sem alterar o zip. Um ano já convertido é pulado (use --forcar para refazer).
"""
import json
import shutil
import time
import zipfile
from pathlib import Path

from swsurv.bdgd import CAMADAS, achar_zip, camadas_para_parquet, fonte_do_zip
from swsurv.config import Config, parser

ARCGIS = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"

ap = parser(__doc__)
ap.add_argument("anos", nargs="*", type=int, help="anos a processar (padrão: todos os snapshots da configuração)")
ap.add_argument("--zips", default=None, help="pasta com os zips já baixados (em vez de baixar do ArcGIS)")
ap.add_argument("--forcar", action="store_true", help="refaz também os anos que já estão convertidos (só com --zips)")
args = ap.parse_args()
cfg = Config.load(args.config)
anos = args.anos or sorted(cfg["bdgd"]["snapshots"])
pasta_zips = cfg.zips_locais(args.zips)


def baixa(item: str, dest: Path) -> Path:
    import requests  # só o download precisa de rede

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


def do_zip_local(ano: int) -> None:
    item = cfg["bdgd"]["snapshots"][ano]
    z = achar_zip(pasta_zips, ano, item, cfg.padrao_zip)
    destino = cfg.cache / str(ano)
    marca = destino / "_origem.json"
    assinatura = {"zip": z.name, "bytes": z.stat().st_size, "item": item}
    if not args.forcar and marca.exists():
        ant = json.loads(marca.read_text(encoding="utf-8"))
        if {k: ant.get(k) for k in assinatura} == assinatura and all(
                (destino / f"{c}.parquet").exists() for c in ant.get("camadas", {})):
            print(ano, "já convertido (pulado)", flush=True)
            return
    t0 = time.time()
    linhas = camadas_para_parquet(fonte_do_zip(z), destino, CAMADAS)
    marca.write_text(json.dumps({**assinatura, "camadas": linhas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(ano, "ok", linhas, f"{time.time() - t0:.0f}s", flush=True)


def do_arcgis(ano: int) -> None:
    tmp = cfg.cache / "_raw" / str(ano)
    gdb = baixa(cfg["bdgd"]["snapshots"][ano], tmp)
    camadas_para_parquet(gdb, cfg.cache / str(ano), CAMADAS)
    shutil.rmtree(tmp, ignore_errors=True)
    print(ano, "ok", flush=True)


for ano in anos:
    (do_zip_local if pasta_zips else do_arcgis)(ano)
