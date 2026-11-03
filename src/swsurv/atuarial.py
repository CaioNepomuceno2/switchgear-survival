"""Método atuarial de taxas de retirada (tábua de vida) e curva de Weibull.

Dados: exposição E(a) e baixas R(a) por idade a (anos completos no início do ano),
somados sobre safras e anos de experiência. Os ativos já existentes no primeiro
cadastro entram na observação com a idade que tinham (truncamento à esquerda) e os
que seguem em operação no último cadastro são censurados à direita: a tábua de vida
usa, para cada idade, só quem estava em risco naquela idade, o que trata os dois casos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def por_idade(mov: pd.DataFrame) -> pd.DataFrame:
    g = mov.groupby("idade")[["expostos", "baixas"]].sum()
    return g[g.expostos > 0].sort_index()


def tabua_de_vida(mov: pd.DataFrame, z: float = 1.645) -> pd.DataFrame:
    """Sobrevivência empírica S(x) = prod_{a<x}(1 - q_a), com IC de Greenwood (log)."""
    g = por_idade(mov).copy()
    g["q"] = g.baixas / g.expostos
    idades = np.arange(0, int(g.index.max()) + 1)
    g = g.reindex(idades)
    q = g.q.fillna(0.0).to_numpy()
    e = g.expostos.fillna(0).to_numpy()
    s = np.cumprod(1 - q)
    with np.errstate(divide="ignore", invalid="ignore"):
        var_terms = np.where((e > 0) & (q < 1), q / (e * (1 - q)), 0.0)
    v = np.cumsum(var_terms)
    out = pd.DataFrame({"idade_fim": idades + 1, "expostos": e, "baixas": g.baixas.fillna(0).to_numpy(),
                        "q": q, "S": s,
                        "S_inf": np.exp(np.log(np.maximum(s, 1e-12)) - z * np.sqrt(v)),
                        "S_sup": np.minimum(np.exp(np.log(np.maximum(s, 1e-12)) + z * np.sqrt(v)), 1.0)})
    return out


def weibull_S(x, beta, eta):
    x = np.maximum(np.asarray(x, dtype=float), 0.0)
    return np.exp(-(x / eta) ** beta)


def weibull_q(idade, beta, eta, meio_ano: float = 0.5):
    """Probabilidade de baixa entre a e a+1 dado sobreviver até a (idade medida a partir do
    meio do ano de imobilização: x0 = a + meio_ano)."""
    x0 = np.maximum(np.asarray(idade, dtype=float) + meio_ano, 0.0)
    h = (np.minimum((x0 + 1.0) / eta, 1e6)) ** beta - (np.minimum(x0 / eta, 1e6)) ** beta
    return -np.expm1(-h)


def ajusta_weibull(mov: pd.DataFrame, chute=(1.5, 40.0)) -> dict:
    """MLE binomial agrupado: R(a) ~ Binomial(E(a), q(a; beta, eta))."""
    g = por_idade(mov)
    a, e, r = g.index.to_numpy(float), g.expostos.to_numpy(float), g.baixas.to_numpy(float)

    def nll(p):
        beta, eta = np.exp(p)
        q = np.clip(weibull_q(a, beta, eta), 1e-12, 1 - 1e-12)
        return -np.sum(r * np.log(q) + (e - r) * np.log1p(-q))

    best = None
    for b0 in (0.7, 1.0, chute[0], 3.0):
        for e0 in (20.0, chute[1], 80.0, 200.0):
            res = minimize(nll, np.log([b0, e0]), method="Nelder-Mead",
                           options={"xatol": 1e-6, "fatol": 1e-8, "maxiter": 4000})
            if best is None or res.fun < best.fun:
                best = res
    beta, eta = np.exp(best.x)
    return {"beta": float(beta), "eta": float(eta), "nll": float(best.fun),
            "mediana": float(eta * np.log(2) ** (1 / beta)),
            "taxa_bruta": float(r.sum() / e.sum()) if e.sum() else np.nan,
            "expostos": float(e.sum()), "baixas": float(r.sum()),
            "idade_max_observada": int(a.max()) if len(a) else 0}


def bootstrap_weibull(mov: pd.DataFrame, b: int = 500, seed: int = 0) -> pd.DataFrame:
    """Bootstrap por safra (reamostra safras inteiras com reposição) e reajusta."""
    rng = np.random.default_rng(seed)
    safras = mov.safra.unique()
    grupos = {v: d for v, d in mov.groupby("safra")}
    out = []
    for _ in range(b):
        amostra = rng.choice(safras, size=len(safras), replace=True)
        m = pd.concat([grupos[v] for v in amostra], ignore_index=True)
        if m.baixas.sum() == 0:
            continue
        f = ajusta_weibull(m)
        out.append({k: f[k] for k in ("beta", "eta", "mediana", "taxa_bruta")})
    return pd.DataFrame(out)


def ic(s: pd.Series, nivel: float = 0.90) -> tuple[float, float]:
    a = (1 - nivel) / 2
    return float(s.quantile(a)), float(s.quantile(1 - a))
