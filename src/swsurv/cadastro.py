"""Leitura do cadastro (BDGD) e montagem da matriz safra x cadastro por classe de ativo.

Por que safras e não equipamento a equipamento: na BDGD da EMT a data de imobilização
(DAT_IMO) do MESMO equipamento (mesmo COD_ID) muda de um ano para o outro na maior parte
dos casos, e os COD_ID são renumerados em massa em alguns anos (2019->2020, 2022->2023).
Já a contagem de equipamentos por ano de imobilização (safra) é estável e só cai, ano a ano,
com as baixas. É o mesmo tipo de dado usado em estudos de depreciação de concessionárias
("aged data"), e o método atuarial de taxas de retirada é o adequado para ele.
"""
from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

ANO_MIN_SAFRA = 1950


def _s(x: pd.Series) -> pd.Series:
    return x.astype("string").str.strip()


def safra(dat_imo: pd.Series, ano_cadastro: int) -> pd.Series:
    """Ano de imobilização (safra) a partir de DAT_IMO (dd/mm/aaaa); inválidas viram NA.

    Inválidas: vazias, '0', anteriores a 1950 (inclui a data-padrão 01/01/1920) e
    posteriores ao ano do cadastro.
    """
    v = pd.to_numeric(_s(dat_imo).str[-4:], errors="coerce")
    ok = v.between(ANO_MIN_SAFRA, ano_cadastro)
    return v.where(ok).astype("Int64")


def ler_classe(cache: Path, ano: int, camada: str, tuc: str, cod_aneel: int | str | None = None) -> pd.DataFrame:
    """Equipamentos de uma classe (TUC) num cadastro: COD_ID, safra e atributos.

    `cod_aneel` (405 = Energisa MT, 404 = Energisa MS), se dado, confere a coluna DIST da BDGD: um cache de
    outra distribuidora (por exemplo SWSURV_CACHE apontando para a pasta errada) para a execução em vez de
    produzir resultados da empresa errada sem aviso.
    """
    df = pd.read_parquet(cache / str(ano) / f"{camada}.parquet")
    for c in df.columns:
        if c not in ("lon", "lat"):
            df[c] = _s(df[c])
    if cod_aneel is not None and "DIST" in df:
        fora = df["DIST"].dropna().unique()
        fora = [d for d in fora if d != str(cod_aneel)]
        if fora:
            raise ValueError(f"{cache / str(ano) / f'{camada}.parquet'}: DIST {fora} não é a distribuidora "
                             f"{cod_aneel} da configuração (cache de outra distribuidora?)")
    df = df[df["TUC"] == tuc].copy()
    df["safra"] = safra(df["DAT_IMO"], ano)
    df["ano"] = ano
    cols = [c for c in ["ano", "COD_ID", "safra", "DAT_IMO", "MEI_ISO", "COR_NOM", "UN_SE", "UN_RE"] if c in df]
    return df[cols].reset_index(drop=True)


def matriz_safras(equip: pd.DataFrame) -> pd.DataFrame:
    """Contagem N[safra, ano] (só equipamentos com safra válida)."""
    m = equip.dropna(subset=["safra"]).groupby(["safra", "ano"]).size().unstack(fill_value=0)
    m.index = m.index.astype(int)
    return m.sort_index()


def sem_data(equip: pd.DataFrame) -> pd.Series:
    """Fração de equipamentos sem safra válida, por ano."""
    return equip.groupby("ano")["safra"].apply(lambda s: float(s.isna().mean()))


def movimentos(m: pd.DataFrame, transicoes: list[int]) -> pd.DataFrame:
    """Exposição e baixas por safra e transição t -> t+1.

    Para cada safra v <= t: expostos = N[v, t]; baixas = max(N[v,t] - N[v,t+1], 0);
    acrescimos = max(N[v,t+1] - N[v,t], 0) (entrada tardia em safra antiga: correção
    cadastral). Idade no início do ano t+1: t - v (anos completos de cadastro).
    """
    linhas = []
    for t in transicoes:
        if t not in m.columns or t + 1 not in m.columns:
            continue
        for v in m.index[m.index <= t]:
            n0, n1 = int(m.at[v, t]), int(m.at[v, t + 1])
            if n0 == 0 and n1 == 0:
                continue
            linhas.append({"transicao": t, "safra": int(v), "idade": t - int(v), "expostos": n0,
                           "baixas": max(n0 - n1, 0), "acrescimos": max(n1 - n0, 0)})
    return pd.DataFrame(linhas, columns=["transicao", "safra", "idade", "expostos", "baixas", "acrescimos"])


def qualidade_classe(mov: pd.DataFrame) -> dict:
    """Indicadores de consistência: acréscimos em safras antigas relativos às baixas."""
    b, a = int(mov.baixas.sum()), int(mov.acrescimos.sum())
    return {"baixas": b, "acrescimos_safras_antigas": a, "reversoes": (a / b) if b else np.nan,
            "expostos_ano_medio": float(mov.groupby("transicao").expostos.sum().mean()) if len(mov) else 0.0}


def safras_nao_monotonas(m: pd.DataFrame, anos: list[int], minimo: int = 10) -> float:
    """Fração das safras (com ao menos `minimo` equipamentos) cuja contagem SOBE depois de ter
    caído dentro da janela `anos`. Numa frota real, uma safra só perde equipamentos."""
    cols = [a for a in anos if a in m.columns]
    flags = []
    for v, row in m[cols].iterrows():
        serie = row[[a for a in cols if a >= v]].to_numpy()
        if len(serie) < 3 or serie.max() < minimo:
            continue
        caiu = False
        ruim = False
        for x0, x1 in pairwise(serie):
            if x1 < x0:
                caiu = True
            elif x1 > x0 and caiu:
                ruim = True
                break
        flags.append(ruim)
    return float(np.mean(flags)) if flags else np.nan


def estabilidade_ids(cache: Path, anos: list[int], camada: str, tuc: str,
                     cod_aneel: int | str | None = None) -> pd.DataFrame:
    """Rastreamento equipamento a equipamento entre cadastros consecutivos.

    Mede: fração dos COD_ID que reaparecem; entre os que reaparecem, fração com a
    mesma DAT_IMO, o mesmo meio de isolação e a mesma unidade de instalação.
    """
    linhas = []
    for a in anos[:-1]:
        e0, e1 = ler_classe(cache, a, camada, tuc, cod_aneel), ler_classe(cache, a + 1, camada, tuc, cod_aneel)
        j = e0.merge(e1, on="COD_ID", suffixes=("_0", "_1"))
        un = "UN_SE" if "UN_SE_0" in j else ("UN_RE" if "UN_RE_0" in j else None)
        linhas.append({
            "transicao": f"{a}->{a + 1}", "n": len(e0),
            "cod_id_reaparece": len(j) / len(e0) if len(e0) else np.nan,
            "mesma_dat_imo": float((j.DAT_IMO_0 == j.DAT_IMO_1).mean()) if len(j) else np.nan,
            "mesmo_meio_isolacao": float((j.MEI_ISO_0 == j.MEI_ISO_1).mean())
            if len(j) and "MEI_ISO_0" in j else np.nan,
            "mesma_unidade": float((j[f"{un}_0"] == j[f"{un}_1"]).mean()) if len(j) and un else np.nan,
        })
    return pd.DataFrame(linhas)


def pontos_religador(cache: Path, anos: list[int], tol_m: float = 30.0, tip_unid: str = "32",
                     lat_ref: float = -13.0) -> pd.DataFrame:
    """Rastreamento dos PONTOS de religador (UNSEMT, `tip_unid`; 32 em MT) por COD_ID e, quando o
    COD_ID não reaparece, pela posição (vizinho mais próximo a até `tol_m` metros).

    `lat_ref` (graus) é a latitude usada para converter graus de longitude em metros: -13 vale para MT
    (padrão); outra distribuidora passa a latitude mediana dos seus pontos.
    """
    from scipy.spatial import cKDTree

    def xy(df):
        return np.c_[df.lon.values * 111320 * np.cos(np.radians(lat_ref)), df.lat.values * 110540]

    def ler(a):
        u = pd.read_parquet(cache / str(a) / "UNSEMT.parquet", columns=["COD_ID", "TIP_UNID", "lon", "lat"])
        u["COD_ID"], u["TIP_UNID"] = _s(u.COD_ID), _s(u.TIP_UNID)
        return u[u.TIP_UNID == tip_unid].dropna(subset=["lon", "lat"]).reset_index(drop=True)

    linhas = []
    for a in anos[:-1]:
        u0, u1 = ler(a), ler(a + 1)
        por_id = u0.COD_ID.isin(set(u1.COD_ID))
        d, _ = cKDTree(xy(u1)).query(xy(u0))
        por_pos = (~por_id) & (d <= tol_m)
        sem_par = ~(por_id | por_pos)
        d1, _ = cKDTree(xy(u0)).query(xy(u1))
        novos = (~u1.COD_ID.isin(set(u0.COD_ID))) & (d1 > tol_m)
        linhas.append({"transicao": f"{a}->{a + 1}", "pontos_inicio": len(u0), "pontos_fim": len(u1),
                       "casados_por_id": int(por_id.sum()), "casados_por_posicao": int(por_pos.sum()),
                       "sem_par_retirados": int(sem_par.sum()), "pontos_novos": int(novos.sum())})
    return pd.DataFrame(linhas)
