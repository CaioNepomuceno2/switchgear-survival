import numpy as np
import pandas as pd
import pytest

from swsurv import atuarial as A
from swsurv import cadastro as C
from swsurv import projecao as P


def test_safra_descarta_datas_invalidas():
    s = pd.Series(["31/12/2016", "01/01/1920", "", "0", "10/05/2030", "15/03/1998"])
    v = C.safra(s, 2025)
    assert v.tolist()[0] == 2016 and v.tolist()[5] == 1998
    assert v.isna().tolist() == [False, True, True, True, True, False]


def test_movimentos_exposicao_baixas_e_acrescimos():
    m = pd.DataFrame({2021: [10, 5], 2022: [8, 6], 2023: [8, 6]}, index=[2010, 2015])
    mov = C.movimentos(m, [2021, 2022])
    r = mov.set_index(["transicao", "safra"])
    assert r.loc[(2021, 2010), "idade"] == 11
    assert r.loc[(2021, 2010), "baixas"] == 2 and r.loc[(2021, 2010), "expostos"] == 10
    assert r.loc[(2021, 2015), "acrescimos"] == 1 and r.loc[(2021, 2015), "baixas"] == 0
    q = C.qualidade_classe(mov)
    assert q["baixas"] == 2 and q["acrescimos_safras_antigas"] == 1


def test_safras_nao_monotonas_detecta_contagem_que_volta_a_subir():
    m = pd.DataFrame({2021: [100, 50], 2022: [90, 40], 2023: [90, 60], 2024: [85, 30]}, index=[2000, 2005])
    assert C.safras_nao_monotonas(m, [2021, 2022, 2023, 2024]) == pytest.approx(0.5)


def _cache_pontos(tmp_path):
    """Dois cadastros: os IDs são renumerados, um ponto some, um ponto novo aparece."""
    base = {"TIP_UNID": ["32", "32", "32", "22"], "lon": [-56.0, -56.1, -56.2, -56.3],
            "lat": [-15.0, -15.1, -15.2, -15.3]}
    a0 = pd.DataFrame({"COD_ID": ["A", "B", "C", "X"], **base})
    a1 = pd.DataFrame({"COD_ID": ["A", "B2", "N", "X"], "TIP_UNID": ["32", "32", "32", "22"],
                       "lon": [-56.0, -56.10001, -57.0, -56.3], "lat": [-15.0, -15.1, -16.0, -15.3]})
    for ano, df in [(2022, a0), (2023, a1)]:
        (tmp_path / str(ano)).mkdir()
        df.to_parquet(tmp_path / str(ano) / "UNSEMT.parquet")
    return tmp_path


def test_rastreamento_de_pontos_por_id_e_posicao(tmp_path):
    out = C.pontos_religador(_cache_pontos(tmp_path), [2022, 2023]).iloc[0]
    assert out.casados_por_id == 1          # A
    assert out.casados_por_posicao == 1     # B -> B2 (~1 m)
    assert out.sem_par_retirados == 1       # C
    assert out.pontos_novos == 1            # N


def _simula_cadastros(beta, eta, n_por_safra=4000, safras=range(1980, 2026), anos=range(2020, 2026), seed=1):
    """Frota simulada com vidas Weibull; o cadastro de cada ano só mostra quem está vivo
    (ativos instalados antes de 2020 entram truncados à esquerda; os vivos em 2025 são censurados)."""
    rng = np.random.default_rng(seed)
    linhas = []
    for v in safras:
        vidas = eta * rng.weibull(beta, n_por_safra)
        fim = v + 0.5 + vidas  # instalação no meio do ano de imobilização
        for t in anos:
            if t >= v:
                linhas.append({"safra": v, "ano": t, "n": int((fim > t + 1e-9).sum())})
    m = pd.DataFrame(linhas).pivot(index="safra", columns="ano", values="n").fillna(0).astype(int)
    return m


def test_tabua_e_weibull_recuperam_curva_simulada_com_truncamento():
    beta, eta = 2.5, 30.0
    m = _simula_cadastros(beta, eta)
    mov = C.movimentos(m, [2020, 2021, 2022, 2023, 2024])
    f = A.ajusta_weibull(mov)
    assert f["beta"] == pytest.approx(beta, rel=0.15)
    assert f["eta"] == pytest.approx(eta, rel=0.10)
    tab = A.tabua_de_vida(mov)
    s20 = tab.loc[tab.idade_fim == 20, "S"].item()
    # S empírica na idade 20 (contada desde o fim do ano de imobilização) vs. verdade
    assert s20 == pytest.approx(A.weibull_S(20.5, beta, eta) / A.weibull_S(0.5, beta, eta), abs=0.03)


def test_weibull_q_risco_constante_quando_beta_1():
    q = A.weibull_q(np.array([0, 10, 30]), 1.0, 20.0)
    assert np.allclose(q, 1 - np.exp(-1 / 20))


def test_projecao_reposicao_mantem_frota_e_bate_conta_simples():
    frota = pd.Series({2015: 100.0, 2020: 200.0})
    p = P.projeta(frota, 2025, 2027, beta=1.0, eta=20.0)
    assert p.substituicoes.iloc[0] == pytest.approx(300 * (1 - np.exp(-1 / 20)))
    assert p.substituicoes.iloc[1] == pytest.approx(300 * (1 - np.exp(-1 / 20)), rel=1e-9)


def test_baselines():
    m = pd.DataFrame({2023: [10, 20, 30]}, index=[1999, 2010, 2020])
    assert P.baseline_idade_limite(m, [2023], 25).iloc[0] == 10   # safra 1999 completa 25 anos em 2024
    assert P.baseline_taxa_constante(m, [2023], 0.1).iloc[0] == pytest.approx(6.0)
