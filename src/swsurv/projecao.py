"""Projeção de baixas/substituições e validação contra baselines."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swsurv.atuarial import weibull_q


def projeta(frota: pd.Series, ano_base: int, ano_fim: int, beta: float, eta: float,
            fator_sem_data: float = 1.0) -> pd.DataFrame:
    """Substituições esperadas por ano, com reposição um a um (o substituto entra como safra nova).

    `frota`: contagem por safra no cadastro de `ano_base`. `fator_sem_data` reescala para os
    equipamentos sem data válida (supõe a mesma distribuição de idades). Não inclui expansão.
    """
    n = frota.astype(float).copy()
    linhas = []
    for t in range(ano_base, ano_fim):
        idade = t - n.index.to_numpy()
        q = weibull_q(idade, beta, eta)
        baixas = n.to_numpy() * q
        n = n - baixas
        n.loc[t + 1] = n.get(t + 1, 0.0) + baixas.sum()
        n = n.sort_index()
        idade_media = float(np.average(t + 1 - n.index.to_numpy(), weights=n.to_numpy()))
        linhas.append({"ano": t + 1, "substituicoes": baixas.sum() * fator_sem_data,
                       "idade_media_frota": idade_media})
    return pd.DataFrame(linhas)


def preve_transicoes(m: pd.DataFrame, transicoes: list[int], beta: float, eta: float) -> pd.Series:
    """Baixas previstas em cada transição t->t+1 dado o cadastro real em t."""
    out = {}
    for t in transicoes:
        n = m.loc[m.index <= t, t]
        out[t + 1] = float((n * weibull_q(t - n.index.to_numpy(), beta, eta)).sum())
    return pd.Series(out)


def baseline_taxa_constante(m: pd.DataFrame, transicoes: list[int], taxa: float) -> pd.Series:
    return pd.Series({t + 1: float(m.loc[m.index <= t, t].sum() * taxa) for t in transicoes})


def baseline_idade_limite(m: pd.DataFrame, transicoes: list[int], limite: int) -> pd.Series:
    """Troca tudo que completa `limite` anos no ano: idade t - v == limite - 1 no início."""
    return pd.Series({t + 1: float(m.loc[(m.index <= t) & (t - m.index == limite - 1), t].sum())
                      for t in transicoes})


def baseline_persistencia(observado_ajuste: pd.Series, transicoes: list[int]) -> pd.Series:
    ultimo = float(observado_ajuste.iloc[-1])
    return pd.Series({t + 1: ultimo for t in transicoes})
