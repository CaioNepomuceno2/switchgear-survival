from pathlib import Path

from swsurv.config import CACHE_ENV, ROOT, Config


def _cfg(cache="data/cache"):
    # monta o Config direto do dict: `Config.processed` criaria pastas dentro do repositório
    return Config({"paths": {"cache": cache, "processed": "data/processed"}})


def test_cache_padrao_e_relativo_a_raiz_do_projeto(monkeypatch):
    monkeypatch.delenv(CACHE_ENV, raising=False)
    assert _cfg().cache == ROOT / "data" / "cache"


def test_variavel_de_ambiente_sobrescreve_o_yaml(monkeypatch, tmp_path):
    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "meu_cache"))
    assert _cfg().cache == tmp_path / "meu_cache"


def test_variavel_vazia_ou_so_com_espacos_nao_sobrescreve(monkeypatch):
    for valor in ("", "   "):
        monkeypatch.setenv(CACHE_ENV, valor)
        assert _cfg().cache == ROOT / "data" / "cache"


def test_caminho_relativo_na_variavel_vale_a_partir_da_raiz(monkeypatch):
    monkeypatch.setenv(CACHE_ENV, "outro/cache")
    assert _cfg().cache == ROOT / "outro" / "cache"


def test_caminho_absoluto_no_yaml_e_respeitado(monkeypatch, tmp_path):
    monkeypatch.delenv(CACHE_ENV, raising=False)
    assert _cfg(str(tmp_path)).cache == tmp_path


def test_premissas_reais_usam_o_padrao_relativo(monkeypatch):
    """Guarda o defeito original: o YAML trazia /home/user/bdgd-cache, caminho de outra máquina."""
    monkeypatch.delenv(CACHE_ENV, raising=False)
    cfg = Config.load()
    assert cfg.raw["paths"]["cache"] == "data/cache"
    assert cfg.cache == ROOT / "data" / "cache"
    assert not Path(cfg.raw["paths"]["cache"]).is_absolute()


def test_pasta_do_cache_esta_no_gitignore():
    linhas = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/cache/" in [ln.strip() for ln in linhas]


def test_ler_cache_nao_cria_a_pasta(monkeypatch, tmp_path):
    destino = tmp_path / "nao_existe"
    monkeypatch.setenv(CACHE_ENV, str(destino))
    assert _cfg().cache == destino and not destino.exists()
