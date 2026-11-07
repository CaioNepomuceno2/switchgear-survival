"""Pipeline de ponta a ponta (scripts 01 a 05, como subprocessos) num cache sintético minúsculo e na configuração
real de cada distribuidora, com as pastas de saída trocadas por pastas temporárias.

* MT (configuração padrão), com religador e disjuntor consistentes e chave e regulador não: os arquivos e as colunas
  saem com os mesmos nomes dos resultados publicados em reports/.
* MS (configs/premissas_ems.yaml), com todas as classes inconsistentes, como nos dados reais: o pipeline termina, não
  estima vida nem projeção e escreve só o que cabe a um diagnóstico do cadastro.
Nada aqui lê rede nem a BDGD.
"""
import os
import subprocess
import sys

import pandas as pd
import pytest
import yaml
from sintetico import gerar_cache

from swsurv.config import CACHE_ENV, CONFIG_ENV, ROOT, Config

SCRIPTS = ["01_painel", "02_vida", "03_validacao", "04_projecao", "05_figuras"]
IDS_MS = {2018: "5382c59d7cc7494a9a1f8cd865187457", 2019: "b83ad867a35b43189f41b68988f7f0b6",
          2020: "fe56dce0714f4b6795d3b23130f5898a", 2021: "933af69c57dd41ea8f6048118b8d07e7",
          2022: "ff5242147c86428e88971941a35c7cd1", 2023: "975f18dfdb0c479cb237893c5b296ca9",
          2024: "b7fad4cd388845a08a01643599ec747b", 2025: "9a1ce360865f4358b31e9fb2d016aac9"}


def _roda_pipeline(base, config, **cache_kw):
    cache = base / "cache"
    gerar_cache(cache, **cache_kw)
    cfg = yaml.safe_load((ROOT / "configs" / config).read_text(encoding="utf-8"))
    cfg["paths"] = {"cache": str(cache), "processed": str(base / "processed"), "reports": str(base / "reports")}
    cfg["analise"]["bootstrap"] = 8  # o teste confere a estrutura, não a precisão do intervalo
    arquivo = base / "config.yaml"
    arquivo.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SWSURV_")}
    env.update({"PYTHONUTF8": "1", "MPLBACKEND": "Agg"})
    for s in SCRIPTS:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{s}.py"), "--config", str(arquivo)],
                           check=False, capture_output=True, text=True, env=env, cwd=ROOT)
        assert r.returncode == 0, f"{s}: {r.stderr[-2000:]}"
    return base / "reports"


@pytest.fixture(scope="module")
def saida_mt(tmp_path_factory):
    return _roda_pipeline(tmp_path_factory.mktemp("mt"), "premissas.yaml", cod_aneel=405)


@pytest.fixture(scope="module")
def saida_ms(tmp_path_factory):
    return _roda_pipeline(tmp_path_factory.mktemp("ms"), "premissas_ems.yaml", cod_aneel=404,
                          todas_inconsistentes=True, lon0=-54.6, lat0=-20.5)


# --- MT: nomes dos arquivos e das colunas iguais aos resultados publicados ----------------------------------------

def test_mt_gera_os_mesmos_arquivos_dos_resultados_publicados(saida_mt):
    publicados = ROOT / "reports"
    assert {p.name for p in saida_mt.glob("*.csv")} == {p.name for p in publicados.glob("*.csv")}
    assert {p.name for p in (saida_mt / "figures").glob("*.png")} == {p.name for p in (publicados / "figures").glob("*.png")}


def test_mt_gera_as_mesmas_colunas_dos_resultados_publicados(saida_mt):
    publicados = ROOT / "reports"
    # a tecnologia depende dos valores de MEI_ISO (o cache sintético tem um só)
    for csv in sorted(p.name for p in publicados.glob("*.csv") if not p.name.startswith("tecnologia_")):
        novo = list(pd.read_csv(saida_mt / csv, nrows=0).columns)
        antigo = list(pd.read_csv(publicados / csv, nrows=0).columns)
        assert novo == antigo, csv


def test_mt_classes_consistentes_e_inconsistentes(saida_mt):
    q = pd.read_csv(saida_mt / "qualidade_classes.csv").set_index("classe")
    assert q.confiavel.to_dict() == {"religador": True, "disjuntor": True, "chave": False, "regulador": False}
    resumo = pd.read_csv(saida_mt / "projecao_resumo.csv").set_index("classe")
    assert set(resumo.index) == {"religador", "disjuntor"}
    assert resumo.capex_2026_2035_rs_mi.notna().to_dict() == {"religador": True, "disjuntor": False}


# --- MS: todas as classes inconsistentes ---------------------------------------------------------------------------

def test_ms_nenhuma_classe_passa_e_nao_ha_estimativa(saida_ms):
    q = pd.read_csv(saida_ms / "qualidade_classes.csv").set_index("classe")
    assert list(q.index) == ["religador", "disjuntor", "chave", "regulador"]
    assert not q.confiavel.any()
    assert (q.reversoes_principal > 0.25).all() and (q.safras_nao_monotonas > 0.10).all()
    vida = pd.read_csv(saida_ms / "vida_weibull.csv")
    assert not vida.confiavel.any() and not [c for c in vida.columns if "ic90" in c]  # sem intervalo: sem bootstrap
    idade = pd.read_csv(saida_ms / "idade_frota_2025.csv")
    assert idade.vida_mediana_estimada.isna().all()  # a vida mediana só sai para classe confiável


def test_ms_projecao_e_taxas_saem_so_com_cabecalho(saida_ms):
    for nome in ("projecao.csv", "projecao_resumo.csv", "taxa_por_faixa.csv"):
        d = pd.read_csv(saida_ms / nome)
        assert len(d) == 0 and len(d.columns) > 3, nome
    assert "classe" in pd.read_csv(saida_ms / "projecao_resumo.csv").columns
    assert "novos_por_ano_2021_2025_media" in pd.read_csv(saida_ms / "projecao_resumo.csv").columns


def test_ms_figuras_so_as_do_cadastro(saida_ms):
    assert {p.name for p in (saida_ms / "figures").glob("*.png")} == {
        "03_frota_2025.png", "06_qualidade_cadastro.png", "07_reversoes_por_transicao.png"}


def test_ms_arquivos_de_diagnostico_do_cadastro(saida_ms):
    ids = pd.read_csv(saida_ms / "qualidade_ids.csv")
    assert set(ids.classe) == {"religador", "disjuntor", "chave", "regulador"}
    pts = pd.read_csv(saida_ms / "qualidade_pontos_religador.csv")
    assert pts.transicao.tolist() == [f"{a}->{a + 1}" for a in range(2018, 2025)]  # os 8 snapshots, M10 inclusive
    assert (pts.casados_por_id > 0).all()


# --- configuração real de MS -----------------------------------------------------------------------------------

def test_configuracao_de_ms(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.delenv(CACHE_ENV, raising=False)
    ms, mt = Config.load(ROOT / "configs" / "premissas_ems.yaml"), Config.load()
    assert ms.sigla == "EMS" and ms.cod_aneel == 404 and ms.nome_curto == "Energisa MS"
    # tudo o que é de MS vai para subpastas ems
    assert ms.cache == ROOT / "data" / "cache" / "ems"
    assert ROOT / ms.raw["paths"]["processed"] == ROOT / "data" / "ems" / "processed"
    assert ms.reports == ROOT / "reports" / "ems" and ms.figuras == ROOT / "reports" / "ems" / "figures"
    # os 8 snapshots da versão mais recente de cada ano; ficam de fora o item avulso e a versão antiga de 2023
    assert ms.raw["bdgd"]["snapshots"] == IDS_MS
    usados = set(ms.raw["bdgd"]["snapshots"].values())
    assert "c3585ae516f340b596617827d60da5ef" not in usados and "b8c585ae35224ac8aa0648587ec61bcb" not in usados
    # decisões de docs/decisoes_ems.md
    assert ms.anos == [2020, 2021, 2022, 2023, 2024, 2025] and ms.ano_base == 2025
    assert {k: v["tuc"] for k, v in ms.classes.items()} == {k: v["tuc"] for k, v in mt.classes.items()}
    assert ms.pontos == {"tip_unid": "32", "tol_m": 30.0, "lat_ref": -20.6}
    assert ms.rotular_figuras and ms.zips_locais() is None  # a pasta dos zips não fica no YAML público
    for chave in ("transicoes_principal", "transicoes_sensibilidade", "validacoes", "limite_reversoes",
                  "limite_nao_monotonas", "idade_limite_anos", "bootstrap", "seed"):
        assert ms["analise"][chave] == mt["analise"][chave], chave  # limiares e janelas iguais aos de MT
    assert set(ms["projecao"]["vida_util_regulatoria_anos"].values()) == {None}  # em branco, como em MT


def test_dados_de_ms_nao_vao_para_o_git():
    linhas = [ln.strip() for ln in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "data/ems/" in linhas and "data/cache/" in linhas
