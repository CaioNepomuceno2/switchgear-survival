"""Tábua de vida, curva de Weibull e idade da frota por classe.

Saídas (em <reports>; <base> = último cadastro, 2025):
  vida_weibull.csv     beta, eta, vida mediana (IC 90% por bootstrap de safras), taxa de baixa
  tabua_<classe>.csv   tábua de vida empírica com IC de Greenwood
  idade_frota_<base>.csv distribuição de idade da frota e fração acima da mediana
  tecnologia_religador_<base>.csv meio de isolação por década de imobilização

Outra distribuidora: --config configs/premissas_ems.yaml (ou SWSURV_CONFIG).
"""
import json

import numpy as np
import pandas as pd

from swsurv import atuarial as A
from swsurv import cadastro as C
from swsurv.config import carregar

cfg = carregar(__doc__)
OUT = cfg.reports
OUT.mkdir(parents=True, exist_ok=True)
base = cfg.ano_base
a = cfg["analise"]
nome_sens = a.get("nome_cenario_sensibilidade", "com_2020_2021")
qual = pd.read_csv(OUT / "qualidade_classes.csv").set_index("classe")
eq = pd.read_parquet(cfg.processed / "equipamentos.parquet")

linhas, idades = [], []
for classe in cfg.classes:
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    conf = bool(qual.at[classe, "confiavel"])
    for cenario, trans in [("principal", a["transicoes_principal"]), (nome_sens, a["transicoes_sensibilidade"])]:
        mov = C.movimentos(m, trans)
        f = A.ajusta_weibull(mov)
        reg = {"classe": classe, "cenario": cenario, "confiavel": conf, **f}
        if cenario == "principal":
            A.tabua_de_vida(mov).to_csv(OUT / f"tabua_{classe}.csv", index=False)
            if conf:
                bs = A.bootstrap_weibull(mov, a["bootstrap"], a["seed"])
                bs.to_csv(cfg.processed / f"bootstrap_{classe}.csv", index=False)
                for k in ("beta", "eta", "mediana", "taxa_bruta"):
                    reg[f"{k}_ic90_inf"], reg[f"{k}_ic90_sup"] = A.ic(bs[k])
            # sobrevivência empírica até a maior idade com exposição razoável
            tab = A.tabua_de_vida(mov)
            ok = tab[tab.expostos >= 50]
            reg["idade_max_com_50_expostos"] = int(ok.idade_fim.max() - 1) if len(ok) else 0
            reg["S_empirica_na_idade_max"] = float(ok.S.iloc[-1]) if len(ok) else np.nan
        linhas.append(reg)
    # idade da frota no último cadastro
    f25 = m[base][m[base] > 0]
    idade = base - f25.index.to_numpy()
    principal = next(r for r in linhas if r["classe"] == classe and r["cenario"] == "principal")
    med = principal["mediana"]
    idades.append({"classe": classe, f"frota_datada_{base}": int(f25.sum()),
                   "idade_media": float(np.average(idade, weights=f25)),
                   "idade_mediana": float(np.median(np.repeat(idade, f25.to_numpy()))),
                   "frac_10_anos_ou_mais": float(f25[idade >= 10].sum() / f25.sum()),
                   "frac_20_anos_ou_mais": float(f25[idade >= 20].sum() / f25.sum()),
                   "vida_mediana_estimada": med if principal["confiavel"] else np.nan,
                   "frac_acima_vida_mediana": float(f25[idade >= med].sum() / f25.sum())
                   if principal["confiavel"] else np.nan})

# taxa anual de baixa por faixa de idade (classes confiáveis), janela principal
fx = []
for classe in cfg.classes:
    if not bool(qual.at[classe, "confiavel"]):
        continue
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    mov = C.movimentos(m, a["transicoes_principal"])
    mov["faixa"] = pd.cut(mov.idade, [-1, 4, 9, 14, 19, 24, 29, 200],
                          labels=["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30+"])
    g = mov.groupby("faixa", observed=False)[["expostos", "baixas"]].sum().reset_index()
    g["taxa_anual"] = g.baixas / g.expostos.replace(0, np.nan)
    fx.append(g.assign(classe=classe))
pd.concat(fx).to_csv(OUT / "taxa_por_faixa.csv", index=False)
print(pd.concat(fx).round(4).to_string(index=False))

vida = pd.DataFrame(linhas)
vida.to_csv(OUT / "vida_weibull.csv", index=False)
pd.DataFrame(idades).to_csv(OUT / f"idade_frota_{base}.csv", index=False)

# tecnologia (meio de isolação) dos religadores no último cadastro, por década de imobilização
r25 = eq[(eq.classe == "religador") & (eq.ano == base)].dropna(subset=["safra"]).copy()
r25["decada"] = (r25.safra.astype(int) // 10) * 10
tec = r25.groupby(["decada", "MEI_ISO"]).size().unstack(fill_value=0)
tec.to_csv(OUT / f"tecnologia_religador_{base}.csv")

print(vida.round(3).to_string(index=False))
print(pd.DataFrame(idades).round(3).to_string(index=False))
print(tec)
print(json.dumps({"ok": True}))
