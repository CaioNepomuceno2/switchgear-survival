"""Teste de fumaça do núcleo do pipeline (scripts 01, 02 e 04) num cadastro sintético minúsculo.

Cadastros anuais (Parquet por camada e ano, como o cache real) são gerados aqui, com semente fixa, e
percorrem as funções de src/: leitura da classe -> matriz de safras -> movimentos (painel de baixas) ->
Weibull e tábua de vida (vida) -> bootstrap -> projeção. Sem rede e sem a BDGD. Confere sanidade, não
recuperação fina dos parâmetros (isso é do teste da curva simulada em test_swsurv.py).
"""
import numpy as np
import pandas as pd
import pytest

from swsurv import atuarial as A
from swsurv import cadastro as C
from swsurv import projecao as P
from swsurv.config import CACHE_ENV, Config

ANOS = list(range(2020, 2026))
TRANSICOES = [2021, 2022, 2023, 2024]
BETA, ETA = 2.5, 25.0


def _cadastros_sinteticos(cache, seed=11, n_por_safra=60, safras=range(1985, 2026), n_invalidas=8):
    """Escreve <cache>/<ano>/EQSE.parquet para 2020-2025 com religadores (TUC 345) de vida Weibull.

    Um equipamento da safra v aparece no cadastro do ano t se v <= t e ainda não saiu (instalação no meio
    do ano v). Entram também disjuntores (TUC 210), que a leitura da classe tem que ignorar, e religadores
    com a data-padrão 01/01/1920, que ficam sem safra. Devolve a contagem esperada de religadores por ano.
    """
    rng = np.random.default_rng(seed)
    unidades = []
    for v in safras:
        fim = v + 0.5 + ETA * rng.weibull(BETA, n_por_safra)
        unidades += [{"safra": v, "fim": f} for f in fim]
    unidades = pd.DataFrame(unidades).assign(COD_ID=lambda d: [f"R{i:05d}" for i in range(len(d))])
    esperado = {}
    for t in ANOS:
        vivos = unidades[(unidades.safra <= t) & (unidades.fim > t)]
        rel = pd.DataFrame({"COD_ID": vivos.COD_ID, "TUC": "345",
                            "DAT_IMO": [f"15/06/{v}" for v in vivos.safra], "MEI_ISO": "SF6", "UN_SE": "S1"})
        sem_data = pd.DataFrame({"COD_ID": [f"X{i:03d}" for i in range(n_invalidas)], "TUC": "345",
                                 "DAT_IMO": "01/01/1920", "MEI_ISO": "SF6", "UN_SE": "S1"})
        disj = pd.DataFrame({"COD_ID": [f"D{i:03d}" for i in range(25)], "TUC": "210",
                             "DAT_IMO": "10/10/2010", "MEI_ISO": "OLEO", "UN_SE": "S2"})
        (cache / str(t)).mkdir(parents=True)
        pd.concat([rel, sem_data, disj], ignore_index=True).to_parquet(cache / str(t) / "EQSE.parquet", index=False)
        esperado[t] = len(vivos) + n_invalidas
    return esperado


def _roda_nucleo(cache, cfg):
    """O que scripts/01, 02 e 04 fazem para uma classe, sem gravar nada em data/ ou reports/."""
    spec = cfg.classes["religador"]
    eq = pd.concat([C.ler_classe(cache, ano, spec["camada"], spec["tuc"]) for ano in ANOS], ignore_index=True)
    m = C.matriz_safras(eq)
    mov = C.movimentos(m, TRANSICOES)
    ajuste = A.ajusta_weibull(mov)
    tabua = A.tabua_de_vida(mov)
    boot = A.bootstrap_weibull(mov, b=6, seed=cfg["analise"]["seed"])
    frota = m[2025][m[2025] > 0]
    fator = int((eq.ano == 2025).sum()) / frota.sum()
    proj = P.projeta(frota, 2025, cfg["projecao"]["fim"], ajuste["beta"], ajuste["eta"], fator)
    return eq, m, mov, ajuste, tabua, boot, proj


def test_nucleo_do_pipeline_percorre_painel_vida_e_projecao(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    esperado = _cadastros_sinteticos(cache)
    monkeypatch.setenv(CACHE_ENV, str(cache))
    cfg = Config.load()
    assert cfg.cache == cache  # o cache vem da variável de ambiente, como no uso real

    eq, m, mov, ajuste, tabua, boot, proj = _roda_nucleo(cfg.cache, cfg)

    # painel: só religadores, contagem por ano igual à gerada, datas-padrão sem safra
    assert eq.groupby("ano").size().to_dict() == esperado
    assert 0 < C.sem_data(eq)[2025] < 0.1
    assert m.index.min() >= 1985 and m.index.max() <= 2025
    assert (m.to_numpy() >= 0).all()
    assert int(m[2025].sum()) == esperado[2025] - 8

    # baixas: numa frota simulada só há saídas, então não há acréscimos nem safras que voltam a subir
    q = C.qualidade_classe(mov)
    assert q["baixas"] > 100 and q["acrescimos_safras_antigas"] == 0 and q["reversoes"] == 0
    assert C.safras_nao_monotonas(m, TRANSICOES + [2025]) == 0.0

    # vida: Weibull finito, tábua monótona e dentro de [0, 1]
    assert np.isfinite([ajuste["beta"], ajuste["eta"], ajuste["mediana"]]).all()
    assert 0 < ajuste["beta"] < 10 and 5 < ajuste["eta"] < 100 and 5 < ajuste["mediana"] < 100
    assert ajuste["baixas"] == q["baixas"]
    assert tabua.S.between(0, 1).all() and (tabua.S.diff().dropna() <= 1e-12).all()
    assert (tabua.S_inf <= tabua.S + 1e-12).all() and (tabua.S_sup >= tabua.S - 1e-12).all()
    assert len(boot) > 0 and np.isfinite(boot.to_numpy()).all() and (boot[["beta", "eta"]] > 0).all().all()
    lo, hi = A.ic(boot.mediana)
    assert lo <= hi

    # projeção: um ano por linha, sem substituições negativas, idade média finita
    pj = cfg["projecao"]
    assert proj.ano.tolist() == list(range(pj["inicio"], pj["fim"] + 1))
    assert (proj.substituicoes > 0).all() and np.isfinite(proj.idade_media_frota).all()
    frota = m[2025][m[2025] > 0]
    assert proj.substituicoes.iloc[0] < 0.5 * frota.sum()

    # validação: as baixas previstas pela curva ajustada ficam na ordem de grandeza das observadas
    prev = P.preve_transicoes(m, TRANSICOES, ajuste["beta"], ajuste["eta"])
    assert prev.index.tolist() == [2022, 2023, 2024, 2025]
    assert prev.sum() == pytest.approx(q["baixas"], rel=0.5)


def test_nucleo_do_pipeline_e_deterministico(tmp_path):
    cache = tmp_path / "cache"
    _cadastros_sinteticos(cache)
    cfg = Config({"classes": {"religador": {"camada": "EQSE", "tuc": "345"}},
                  "analise": {"seed": 7}, "projecao": {"inicio": 2026, "fim": 2030}})
    r1, r2 = _roda_nucleo(cache, cfg), _roda_nucleo(cache, cfg)
    assert r1[3] == r2[3]
    pd.testing.assert_frame_equal(r1[5], r2[5])
    pd.testing.assert_frame_equal(r1[6], r2[6])
