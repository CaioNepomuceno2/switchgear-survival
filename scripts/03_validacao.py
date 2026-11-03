"""Validação temporal fora da amostra das baixas anuais por classe.

Para cada desenho em configs (ex.: ajusta com 2022-2023 e prevê 2024-2025), compara a curva
de Weibull com três baselines: taxa constante (baixas/expostos da janela de ajuste),
idade-limite fixa (troca tudo que completa N anos) e persistência (repete o último ano).

Métricas: total previsto vs observado, erro absoluto por ano e "acerto por safra"
(soma de min(previsto, observado) por safra e ano / baixas observadas: quanto das baixas
reais caiu nas safras em que o método esperava baixas).
Saídas: reports/validacao.csv, reports/validacao_resumo.csv, reports/validacao_faixas.csv
"""
import numpy as np
import pandas as pd

from swsurv import atuarial as A
from swsurv import cadastro as C
from swsurv import projecao as P
from swsurv.config import ROOT, Config

cfg = Config.load()
OUT = ROOT / "reports"
a = cfg["analise"]
L = a["idade_limite_anos"]
qual = pd.read_csv(OUT / "qualidade_classes.csv").set_index("classe")
linhas, acerto, faixas = [], [], []
for desenho in a["validacoes"]:
    for classe in cfg.classes:
        m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
        m.columns = m.columns.astype(int)
        mov_aj, mov_te = C.movimentos(m, desenho["ajuste"]), C.movimentos(m, desenho["teste"])
        f = A.ajusta_weibull(mov_aj)
        obs_aj = mov_aj.groupby("transicao").baixas.sum()
        obs = mov_te.groupby("transicao").baixas.sum()
        obs.index = obs.index + 1
        prev = {
            "weibull": P.preve_transicoes(m, desenho["teste"], f["beta"], f["eta"]),
            "taxa_constante": P.baseline_taxa_constante(m, desenho["teste"], f["taxa_bruta"]),
            "idade_limite": P.baseline_idade_limite(m, desenho["teste"], L),
            "persistencia": P.baseline_persistencia(obs_aj, desenho["teste"]),
        }
        base = {"desenho": desenho["nome"], "classe": classe, "confiavel": bool(qual.at[classe, "confiavel"])}
        for metodo, serie in prev.items():
            for ano, v in serie.items():
                linhas.append({**base, "metodo": metodo, "ano": int(ano), "previsto": float(v),
                               "observado": int(obs.get(ano, 0))})
        cel = mov_te.copy()
        cel["weibull"] = cel.expostos * A.weibull_q(cel.idade, f["beta"], f["eta"])
        cel["taxa_constante"] = cel.expostos * f["taxa_bruta"]
        cel["idade_limite"] = np.where(cel.idade == L - 1, cel.expostos, 0.0)
        cel["faixa"] = pd.cut(cel.idade, [-1, 9, 19, 200], labels=["0-9", "10-19", "20+"])
        for metodo in ("weibull", "taxa_constante", "idade_limite"):
            acerto.append({**base, "metodo": metodo,
                           "acerto_por_safra": float(np.minimum(cel[metodo], cel.baixas).sum()
                                                     / max(cel.baixas.sum(), 1))})
            fx = cel.groupby("faixa", observed=False)[[metodo, "baixas"]].sum().reset_index()
            faixas += [{**base, "metodo": metodo, "faixa": r.faixa, "previsto": r[metodo], "observado": r.baixas}
                       for _, r in fx.iterrows()]

val = pd.DataFrame(linhas)
val["erro_abs"] = (val.previsto - val.observado).abs()
resumo = (val.groupby(["desenho", "classe", "confiavel", "metodo"])
          .agg(previsto=("previsto", "sum"), observado=("observado", "sum"), erro_abs_medio=("erro_abs", "mean"))
          .reset_index())
resumo = resumo.merge(pd.DataFrame(acerto), on=["desenho", "classe", "confiavel", "metodo"], how="left")
resumo["erro_total_pct"] = 100 * (resumo.previsto / resumo.observado.replace(0, np.nan) - 1)
val.to_csv(OUT / "validacao.csv", index=False)
resumo.to_csv(OUT / "validacao_resumo.csv", index=False)
pd.DataFrame(faixas).to_csv(OUT / "validacao_faixas.csv", index=False)
print(resumo[resumo.confiavel].round(2).to_string(index=False))
