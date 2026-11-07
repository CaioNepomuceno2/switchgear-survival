import pytest

from swsurv.config import CACHE_ENV, CONFIG_ENV, ZIPS_ENV


@pytest.fixture(autouse=True)
def _sem_variaveis_de_configuracao(monkeypatch):
    """Nenhum teste herda SWSURV_CONFIG, SWSURV_CACHE ou SWSURV_BDGD_ZIPS do ambiente de quem roda; os testes que
    precisam de uma delas a definem."""
    for nome in (CONFIG_ENV, CACHE_ENV, ZIPS_ENV):
        monkeypatch.delenv(nome, raising=False)
