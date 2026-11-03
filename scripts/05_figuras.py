"""Figuras do README (reports/figures)."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from swsurv import atuarial as A
from swsurv.config import ROOT, Config

plt.switch_backend("Agg")

cfg = Config.load()
R = ROOT / "reports"
F = R / "figures"
F.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.size": 10})
COR = {"religador": "#1f6fb2", "disjuntor": "#d9822b", "chave": "#7f7f7f", "regulador": "#8c564b"}
vida = pd.read_csv(R / "vida_weibull.csv")
pr = vida[vida.cenario == "principal"].set_index("classe")

# 1. sobrevivência: tábua empírica + Weibull
fig, ax = plt.subplots(figsize=(8, 4.6))
x = np.linspace(0, 60, 300)
for classe in ["religador", "disjuntor"]:
    t = pd.read_csv(R / f"tabua_{classe}.csv")
    t = t[t.expostos >= 30]
    v = pr.loc[classe]
    ax.step(np.r_[0, t.idade_fim], np.r_[1, t.S], where="post", color=COR[classe], lw=1.6,
            label=f"{cfg.classes[classe]['nome']}: observado")
    ax.fill_between(np.r_[0, t.idade_fim], np.r_[1, t.S_inf], np.r_[1, t.S_sup], step="post",
                    color=COR[classe], alpha=0.15)
    ax.plot(x, A.weibull_S(x - 0.5, v.beta, v.eta), color=COR[classe], ls="--", lw=1.2,
            label=f"Weibull (vida mediana {v.mediana:.0f} anos, IC 90% {v.mediana_ic90_inf:.0f}-{v.mediana_ic90_sup:.0f})")
ax.axhline(0.5, color="k", lw=0.6, alpha=0.5)
ax.set(xlabel="idade (anos desde a imobilização)", ylabel="fração ainda em operação", ylim=(0, 1.02), xlim=(0, 60),
       title="Curva de sobrevivência: observado (2022-2025) e extrapolação de Weibull")
ax.legend(fontsize=8, loc="lower left")
fig.tight_layout()
fig.savefig(F / "01_sobrevivencia.png")

# 2. taxa anual de baixa por faixa de idade
fx = pd.read_csv(R / "taxa_por_faixa.csv")
fig, ax = plt.subplots(figsize=(8, 4))
faixas = fx.faixa.unique()
w = 0.38
for i, classe in enumerate(["religador", "disjuntor"]):
    d = fx[fx.classe == classe].set_index("faixa").reindex(faixas)
    pos = np.arange(len(faixas)) + (i - 0.5) * w
    ax.bar(pos, 100 * d.taxa_anual.fillna(0), width=w, color=COR[classe], label=cfg.classes[classe]["nome"])
    for p_, (tx, b, e) in zip(pos, d[["taxa_anual", "baixas", "expostos"]].itertuples(index=False)):
        if e and e > 0:
            ax.text(p_, 100 * (0 if pd.isna(tx) else tx) + 0.3, f"{int(b)}/{int(e)}", ha="center", fontsize=6.5)
ax.set_xticks(np.arange(len(faixas)), faixas)
ax.set(xlabel="faixa de idade (anos)", ylabel="% baixados no ano",
       title="Taxa anual de baixa por idade (2022-2025): o risco cresce com a idade")
ax.legend()
fig.tight_layout()
fig.savefig(F / "02_taxa_por_idade.png")

# 3. pirâmide etária da frota 2025 + tecnologia
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for classe in ["religador", "disjuntor"]:
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    f25 = m[2025][m[2025] > 0]
    axes[0].bar(f25.index, f25.values, color=COR[classe], alpha=0.8, label=cfg.classes[classe]["nome"])
axes[0].set(xlabel="ano de imobilização (safra)", ylabel="equipamentos no cadastro 2025",
            title="Frota 2025 por safra")
axes[0].legend(fontsize=8)
tec = pd.read_csv(R / "tecnologia_religador_2025.csv").set_index("decada")
tec.plot(kind="bar", stacked=True, ax=axes[1], color=["#2ca02c", "#9467bd", "#1f6fb2"][: tec.shape[1]])
axes[1].set(xlabel="década de imobilização", ylabel="religadores (2025)",
            title="Religadores: meio de isolação por década (código BDGD)")
axes[1].legend(title="MEI_ISO", fontsize=8)
fig.tight_layout()
fig.savefig(F / "03_frota_2025.png")

# 4. projeção de substituições de religadores e CAPEX ilustrativo
pj = pd.read_csv(R / "projecao.csv")
res = pd.read_csv(R / "projecao_resumo.csv").set_index("classe")
d = pj[pj.classe == "religador"]
fig, ax = plt.subplots(figsize=(8, 4.2))
ax.bar(d.ano, d.substituicoes, color=COR["religador"], label="substituições esperadas")
ax.errorbar(d.ano, d.substituicoes, yerr=[d.substituicoes - d.ic90_inf, d.ic90_sup - d.substituicoes],
            fmt="none", ecolor="k", capsize=3, lw=0.8, label="IC 90% (bootstrap)")
novos = res.at["religador", "novos_por_ano_2021_2025_media"]
ax.axhline(novos, color="#d62728", ls="--", lw=1, label=f"religadores novos por ano em 2021-2025 (média {novos:.0f})")
for _, r in d.iterrows():
    ax.text(r.ano, r.ic90_sup + 4, f"R$ {r.capex_rs_mi:.0f} mi", ha="center", fontsize=7)
ax.set(xlabel="ano", ylabel="religadores", title="Religadores: substituições esperadas 2026-2035 (CAPEX com custo ilustrativo)")
ax.legend(fontsize=8, loc="upper left")
fig.tight_layout()
fig.savefig(F / "04_projecao_religadores.png")

# 5. validação (religador)
val = pd.read_csv(R / "validacao.csv")
v = val[(val.classe == "religador") & (val.desenho == val.desenho.iloc[0])]
fig, ax = plt.subplots(figsize=(7.5, 4))
metodos = ["weibull", "taxa_constante", "idade_limite", "persistencia"]
nomes = {"weibull": "Weibull", "taxa_constante": "taxa constante", "idade_limite": "idade-limite 25 anos",
         "persistencia": "persistência"}
anos = sorted(v.ano.unique())
w = 0.16
for i, mt in enumerate(metodos):
    d = v[v.metodo == mt].set_index("ano").reindex(anos)
    ax.bar(np.arange(len(anos)) + (i - 1.5) * w, d.previsto, width=w, label=nomes[mt])
obs = v[v.metodo == "weibull"].set_index("ano").reindex(anos).observado
ax.scatter(np.arange(len(anos)) + 0.45, obs, color="k", zorder=3, marker="D", label="observado")
ax.set_xticks(np.arange(len(anos)), anos)
ax.set(ylabel="religadores baixados", title="Validação fora da amostra (ajuste com 2022-2023)")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(F / "05_validacao.png")

# 6. qualidade do cadastro: safras de religador (estáveis) vs reguladores (instáveis)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True)
for ax, classe in zip(axes, ["religador", "regulador"]):
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    top = m[[c for c in m.columns if c >= 2020]].loc[lambda d: d.index <= 2020]
    top = top.loc[top.max(axis=1).sort_values(ascending=False).index[:8]]
    for v_, row in top.iterrows():
        ax.plot(row.index, row.values, marker="o", ms=3, lw=1, label=str(v_))
    ax.set(title=f"{cfg.classes[classe]['nome']}: contagem por safra", xlabel="cadastro (31/12)")
    ax.legend(title="safra", fontsize=7, ncol=2)
axes[0].set_ylabel("equipamentos")
fig.tight_layout()
fig.savefig(F / "06_qualidade_cadastro.png")
print("ok")
