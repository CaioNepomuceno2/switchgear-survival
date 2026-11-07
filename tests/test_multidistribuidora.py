"""Configuração por distribuidora: o padrão continua sendo MT (mesmos caminhos e nomes dos resultados publicados)
e a Energisa MS entra por --config ou SWSURV_CONFIG, escrevendo só em subpastas ems."""
import subprocess
import sys

import pandas as pd
import pytest
import yaml

from swsurv import cadastro as C
from swsurv.config import CACHE_ENV, CONFIG_ENV, ROOT, Config


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.delenv(CACHE_ENV, raising=False)


# --- guarda de MT: a configuração padrão resolve exatamente o que os resultados publicados usam ----------------

def test_padrao_e_a_configuracao_de_mt():
    cfg = Config.load()
    assert cfg.origem == ROOT / "configs" / "premissas.yaml"
    assert cfg.sigla == "EMT" and cfg.cod_aneel == 405 and cfg.nome_curto == "Energisa MT"
    assert cfg.cache == ROOT / "data" / "cache"
    assert ROOT / cfg.raw["paths"]["processed"] == ROOT / "data" / "processed"  # sem criar a pasta
    assert cfg.reports == ROOT / "reports" and cfg.figuras == ROOT / "reports" / "figures"
    assert cfg.anos == [2020, 2021, 2022, 2023, 2024, 2025] and cfg.ano_base == 2025
    assert cfg.anos_snapshots == list(range(2018, 2026))
    assert cfg.pontos == {"tip_unid": "32", "tol_m": 30.0, "lat_ref": -13.0}
    assert cfg.zips_locais() is None and cfg.rotular_figuras is False
    assert cfg.titulo("Título") == "Título"  # as figuras de MT não ganham rótulo
    assert {k: v["tuc"] for k, v in cfg.classes.items()} == {"religador": "345", "disjuntor": "210",
                                                              "chave": "160", "regulador": "340"}


def test_resultados_publicados_de_mt_estao_na_pasta_que_a_configuracao_padrao_aponta():
    cfg = Config.load()
    for nome in ("vida_weibull.csv", "projecao_resumo.csv", "qualidade_classes.csv", "validacao_resumo.csv"):
        assert (cfg.reports / nome).is_file()


def test_nomes_derivados_da_configuracao_de_mt_batem_com_os_cabecalhos_publicados():
    """Os scripts montam colunas e arquivos com o ano-base e o sufixo da sensibilidade: em MT dão os nomes de sempre."""
    cfg = Config.load()
    base, suf = cfg.ano_base, cfg["analise"].get("sufixo_sensibilidade", "com_2021")
    cab = list(pd.read_csv(cfg.reports / "qualidade_classes.csv", nrows=0).columns)
    assert f"frota_{base}" in cab and f"sem_data_{base}" in cab
    assert {f"baixas_{suf}", f"acrescimos_{suf}", f"reversoes_{suf}"} <= set(cab)
    resumo = list(pd.read_csv(cfg.reports / "projecao_resumo.csv", nrows=0).columns)
    assert {f"frota_{base}", f"frac_da_frota_{base}", f"novos_por_ano_{cfg.anos[1]}_{base}_media"} <= set(resumo)
    assert (cfg.reports / f"idade_frota_{base}.csv").is_file()
    assert (cfg.reports / f"tecnologia_religador_{base}.csv").is_file()
    vida = pd.read_csv(cfg.reports / "vida_weibull.csv")
    assert cfg["analise"].get("nome_cenario_sensibilidade", "com_2020_2021") in set(vida.cenario)


# --- escolha da configuração -----------------------------------------------------------------------------------

def _yaml(tmp_path, nome, cache):
    p = tmp_path / nome
    p.write_text(yaml.safe_dump({"distribuidora": nome, "paths": {"cache": cache, "processed": "x", "reports": "r"}}),
                 encoding="utf-8")
    return p


def test_argumento_vence_variavel_que_vence_o_padrao(monkeypatch, tmp_path):
    arg, env = _yaml(tmp_path, "ARG", "a"), _yaml(tmp_path, "ENV", "e")
    assert Config.load().sigla == "EMT"
    monkeypatch.setenv(CONFIG_ENV, str(env))
    assert Config.load().sigla == "ENV"
    assert Config.load(arg).sigla == "ARG"
    monkeypatch.setenv(CONFIG_ENV, "  ")
    assert Config.load().sigla == "EMT"  # variável vazia não conta


def test_config_relativa_vale_a_partir_da_raiz_do_projeto(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # fora do repositório
    assert Config.load("configs/premissas.yaml").origem == ROOT / "configs" / "premissas.yaml"
    with pytest.raises(FileNotFoundError):
        Config.load("configs/nao_existe.yaml")


def test_swsurv_cache_continua_valendo_para_qualquer_configuracao(monkeypatch, tmp_path):
    for nome in ("premissas.yaml", "premissas_ems.yaml"):
        monkeypatch.delenv(CACHE_ENV, raising=False)
        assert Config.load(ROOT / "configs" / nome).cache.is_relative_to(ROOT / "data" / "cache")
        monkeypatch.setenv(CACHE_ENV, str(tmp_path / "outro"))
        assert Config.load(ROOT / "configs" / nome).cache == tmp_path / "outro"


def test_scripts_documentam_e_leem_o_argumento_config(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "01_painel.py"), "--help"], check=False, capture_output=True,
                       text=True, cwd=ROOT)
    assert r.returncode == 0 and "--config" in r.stdout and CONFIG_ENV in r.stdout
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "01_painel.py"), "--config", str(tmp_path / "x.yaml")],
                       check=False, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0 and "FileNotFoundError" in r.stderr  # o argumento chega à Config.load


# --- guarda de distribuidora: cache de outra empresa para a execução -----------------------------------------------

def _cache_eqse(tmp_path, dist):
    d = tmp_path / "2025"
    d.mkdir(parents=True)
    pd.DataFrame({"COD_ID": ["a", "b"], "DIST": [dist, dist], "TUC": ["345", "345"],
                  "DAT_IMO": ["01/01/2010", "01/01/2011"]}).to_parquet(d / "EQSE.parquet", index=False)
    return tmp_path


def test_cache_de_outra_distribuidora_e_recusado(tmp_path):
    cache = _cache_eqse(tmp_path, 404)  # cadastro da Energisa MS
    assert len(C.ler_classe(cache, 2025, "EQSE", "345", cod_aneel=404)) == 2
    assert len(C.ler_classe(cache, 2025, "EQSE", "345")) == 2  # sem código na configuração: não confere
    with pytest.raises(ValueError, match="outra distribuidora"):
        C.ler_classe(cache, 2025, "EQSE", "345", cod_aneel=405)  # configuração de MT lendo o cache de MS


def test_pontos_de_religador_usam_a_latitude_da_configuracao(tmp_path):
    """A conversão de graus em metros depende da latitude: -13 (MT, padrão) e -20,6 (MS) casam pontos a 30 m
    de forma diferente quando o deslocamento é só em longitude."""
    for ano, lon in [(2022, -54.0), (2023, -54.0 + 0.00028)]:  # 0,00028 grau de longitude = 31,2 m no equador
        (tmp_path / str(ano)).mkdir()
        pd.DataFrame({"COD_ID": [f"P{ano}"], "TIP_UNID": ["32"], "lon": [lon], "lat": [-20.0]}).to_parquet(
            tmp_path / str(ano) / "UNSEMT.parquet")
    # distância = 31,2 m * cos(latitude de referência): 30,4 m com -13 (acima de 30 m) e 29,2 m com -20,6 (abaixo)
    mt = C.pontos_religador(tmp_path, [2022, 2023]).iloc[0]
    ms = C.pontos_religador(tmp_path, [2022, 2023], lat_ref=-20.6).iloc[0]
    assert mt.casados_por_posicao == 0 and ms.casados_por_posicao == 1
    assert C.pontos_religador(tmp_path, [2022, 2023], tip_unid="22").iloc[0].pontos_inicio == 0
