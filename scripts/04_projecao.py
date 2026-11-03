"""Projeção 2026-2035 de substituições (reposição de baixas) e CAPEX ilustrativo.

Para as classes confiáveis: a frota datada de 2025 é envelhecida ano a ano com a curva de
Weibull; cada baixa é reposta por um equipamento novo. IC 90% com os parâmetros do bootstrap
por safra. Não inclui expansão da rede (equipamentos novos em pontos novos).
Saídas: reports/projecao.csv, reports/projecao_resumo.csv
"""
import numpy as np
import pandas as pd

from swsurv import projecao as P
from swsurv.config import ROOT, Config

cfg = Config.load()
OUT = ROOT / "reports"
pj = cfg["projecao"]
vida = pd.read_csv(OUT / "vida_weibull.csv")
eq = pd.read_parquet(cfg.processed / "equipamentos.parquet")
linhas, resumo = [], []
for classe in cfg.classes:
    v = vida[(vida.classe == classe) & (vida.cenario == "principal")].iloc[0]
    if not v.confiavel:
        continue
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    frota = m[2025][m[2025] > 0]
    total = int((eq[(eq.classe == classe) & (eq.ano == 2025)]).shape[0])
    fator = total / frota.sum()
    base = P.projeta(frota, 2025, pj["fim"], v.beta, v.eta, fator)
    bs = pd.read_csv(cfg.processed / f"bootstrap_{classe}.csv")
    sims = np.array([P.projeta(frota, 2025, pj["fim"], b.beta, b.eta, fator).substituicoes.to_numpy()
                     for b in bs.itertuples()])
    custo = pj["custo_unitario_rs"].get(classe)
    for i, r in base.iterrows():
        lo, hi = np.quantile(sims[:, i], [0.05, 0.95])
        linhas.append({"classe": classe, "ano": int(r.ano), "substituicoes": r.substituicoes,
                       "ic90_inf": lo, "ic90_sup": hi, "idade_media_frota": r.idade_media_frota,
                       "capex_rs_mi": r.substituicoes * custo / 1e6 if custo else np.nan})
    tot = sims.sum(axis=1)
    resumo.append({"classe": classe, "frota_2025": total, "substituicoes_2026_2035": base.substituicoes.sum(),
                   "ic90_inf": np.quantile(tot, 0.05), "ic90_sup": np.quantile(tot, 0.95),
                   "frac_da_frota_2025": base.substituicoes.sum() / total,
                   "capex_2026_2035_rs_mi": base.substituicoes.sum() * custo / 1e6 if custo else np.nan,
                   "custo_unitario_rs_ilustrativo": custo})
    # contexto: entrada de equipamentos novos (safra = ano do cadastro) observada
    novos = {t: int(m.at[t, t]) if t in m.index else 0 for t in range(2021, 2026)}
    resumo[-1]["novos_por_ano_2021_2025_media"] = float(np.mean(list(novos.values())))

proj = pd.DataFrame(linhas)
proj.to_csv(OUT / "projecao.csv", index=False)
pd.DataFrame(resumo).to_csv(OUT / "projecao_resumo.csv", index=False)
print(proj.round(1).to_string(index=False))
print(pd.DataFrame(resumo).round(2).to_string(index=False))
