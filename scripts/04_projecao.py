"""Projeção 2026-2035 de substituições (reposição de baixas) e CAPEX ilustrativo.

Para as classes confiáveis: a frota datada de 2025 é envelhecida ano a ano com a curva de
Weibull; cada baixa é reposta por um equipamento novo. IC 90% com os parâmetros do bootstrap
por safra. Não inclui expansão da rede (equipamentos novos em pontos novos).
Saídas (em <reports>): projecao.csv, projecao_resumo.csv
Outra distribuidora: --config configs/premissas_ems.yaml (ou SWSURV_CONFIG).
"""
import numpy as np
import pandas as pd

from swsurv import projecao as P
from swsurv.config import carregar

cfg = carregar(__doc__)
OUT = cfg.reports
base_ano = cfg.ano_base
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
    frota = m[base_ano][m[base_ano] > 0]
    total = int((eq[(eq.classe == classe) & (eq.ano == base_ano)]).shape[0])
    fator = total / frota.sum()
    base = P.projeta(frota, base_ano, pj["fim"], v.beta, v.eta, fator)
    bs = pd.read_csv(cfg.processed / f"bootstrap_{classe}.csv")
    sims = np.array([P.projeta(frota, base_ano, pj["fim"], b.beta, b.eta, fator).substituicoes.to_numpy()
                     for b in bs.itertuples()])
    custo = pj["custo_unitario_rs"].get(classe)
    for i, r in base.iterrows():
        lo, hi = np.quantile(sims[:, i], [0.05, 0.95])
        linhas.append({"classe": classe, "ano": int(r.ano), "substituicoes": r.substituicoes,
                       "ic90_inf": lo, "ic90_sup": hi, "idade_media_frota": r.idade_media_frota,
                       "capex_rs_mi": r.substituicoes * custo / 1e6 if custo else np.nan})
    tot = sims.sum(axis=1)
    resumo.append({"classe": classe, f"frota_{base_ano}": total, "substituicoes_2026_2035": base.substituicoes.sum(),
                   "ic90_inf": np.quantile(tot, 0.05), "ic90_sup": np.quantile(tot, 0.95),
                   f"frac_da_frota_{base_ano}": base.substituicoes.sum() / total,
                   "capex_2026_2035_rs_mi": base.substituicoes.sum() * custo / 1e6 if custo else np.nan,
                   "custo_unitario_rs_ilustrativo": custo})
    # contexto: entrada de equipamentos novos (safra = ano do cadastro) observada
    anos_novos = range(cfg.anos[1], base_ano + 1)
    novos = {t: int(m.at[t, t]) if t in m.index else 0 for t in anos_novos}
    resumo[-1][f"novos_por_ano_{anos_novos[0]}_{base_ano}_media"] = float(np.mean(list(novos.values())))

proj = pd.DataFrame(linhas)
proj.to_csv(OUT / "projecao.csv", index=False)
pd.DataFrame(resumo).to_csv(OUT / "projecao_resumo.csv", index=False)
print(proj.round(1).to_string(index=False))
print(pd.DataFrame(resumo).round(2).to_string(index=False))
