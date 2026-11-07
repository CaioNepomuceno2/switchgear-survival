"""Figuras do README (<reports>/figures).

Plota as classes que passaram no teste de consistência (confiavel = True em vida_weibull.csv). Se nenhuma passou
(acontece em MS), saem só as figuras do cadastro: frota por safra (03), qualidade (06) e, se a configuração pedir,
acréscimos contra baixas por transição (07). Os anos dos títulos vêm da configuração.
Outra distribuidora: --config configs/premissas_ems.yaml (ou SWSURV_CONFIG).
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from swsurv import atuarial as A
from swsurv import cadastro as C
from swsurv.config import carregar

plt.switch_backend("Agg")

cfg = carregar(__doc__)
R = cfg.reports
F = cfg.figuras
F.mkdir(parents=True, exist_ok=True)
base = cfg.ano_base
a = cfg["analise"]
pj_cfg = cfg["projecao"]
fig_cfg = cfg.raw.get("figuras", {})
janela = f"{min(a['transicoes_principal']) + 1}-{max(a['transicoes_principal']) + 1}"  # anos dos cadastros da janela
L = a["idade_limite_anos"]
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.size": 10})
COR = {"religador": "#1f6fb2", "disjuntor": "#d9822b", "chave": "#7f7f7f", "regulador": "#8c564b"}
vida = pd.read_csv(R / "vida_weibull.csv")
pr = vida[vida.cenario == "principal"].set_index("classe")
conf = [c for c in cfg.classes if bool(pr.at[c, "confiavel"])]  # classes com estimativa de vida
if not conf:
    print("nenhuma classe passou no teste de consistência: figuras 01, 02, 04 e 05 (vida, projeção, validação) não geradas")


def rotula(fig):
    """Figuras com vários painéis: o nome da distribuidora vai no título geral (só se a configuração pedir)."""
    if cfg.rotular_figuras:
        fig.suptitle(cfg.nome_curto, fontsize=10)


if conf:
    # 1. sobrevivência: tábua empírica + Weibull
    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = np.linspace(0, 60, 300)
    for classe in conf:
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
           title=cfg.titulo(f"Curva de sobrevivência: observado ({janela}) e extrapolação de Weibull"))
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(F / "01_sobrevivencia.png")

    # 2. taxa anual de baixa por faixa de idade
    fx = pd.read_csv(R / "taxa_por_faixa.csv")
    fig, ax = plt.subplots(figsize=(8, 4))
    faixas = fx.faixa.unique()
    w = 0.76 / len(conf)
    for i, classe in enumerate(conf):
        d = fx[fx.classe == classe].set_index("faixa").reindex(faixas)
        pos = np.arange(len(faixas)) + (i - (len(conf) - 1) / 2) * w
        ax.bar(pos, 100 * d.taxa_anual.fillna(0), width=w, color=COR[classe], label=cfg.classes[classe]["nome"])
        for p_, (tx, b, e) in zip(pos, d[["taxa_anual", "baixas", "expostos"]].itertuples(index=False)):
            if e and e > 0:
                ax.text(p_, 100 * (0 if pd.isna(tx) else tx) + 0.3, f"{int(b)}/{int(e)}", ha="center", fontsize=6.5)
    ax.set_xticks(np.arange(len(faixas)), faixas)
    complemento = fig_cfg.get("complemento_taxa", ": o risco cresce com a idade")
    ax.set(xlabel="faixa de idade (anos)", ylabel="% baixados no ano",
           title=cfg.titulo(f"Taxa anual de baixa por idade ({janela}){complemento}"))
    ax.legend()
    fig.tight_layout()
    fig.savefig(F / "02_taxa_por_idade.png")

# 3. pirâmide etária da frota no último cadastro + tecnologia
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for classe in conf or fig_cfg.get("classes_frota", ["religador", "disjuntor"]):
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    f25 = m[base][m[base] > 0]
    axes[0].bar(f25.index, f25.values, color=COR[classe], alpha=0.8, label=cfg.classes[classe]["nome"])
axes[0].set(xlabel="ano de imobilização (safra)", ylabel=f"equipamentos no cadastro {base}",
            title=f"Frota {base} por safra")
axes[0].legend(fontsize=8)
tec = pd.read_csv(R / f"tecnologia_religador_{base}.csv").set_index("decada")
paleta = ["#2ca02c", "#9467bd", "#1f6fb2", "#d9822b", "#7f7f7f", "#8c564b", "#17becf", "#e377c2"]
tec.plot(kind="bar", stacked=True, ax=axes[1], color=paleta[: tec.shape[1]])
axes[1].set(xlabel="década de imobilização", ylabel=f"religadores ({base})",
            title="Religadores: meio de isolação por década (código BDGD)")
axes[1].legend(title="MEI_ISO", fontsize=8)
rotula(fig)
fig.tight_layout()
fig.savefig(F / "03_frota_2025.png")

# 4. projeção de substituições de religadores e CAPEX ilustrativo
pj = pd.read_csv(R / "projecao.csv")
res = pd.read_csv(R / "projecao_resumo.csv").set_index("classe")
val = pd.read_csv(R / "validacao.csv")
d = pj[pj.classe == "religador"]
if "religador" in conf:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(d.ano, d.substituicoes, color=COR["religador"], label="substituições esperadas")
    ax.errorbar(d.ano, d.substituicoes, yerr=[d.substituicoes - d.ic90_inf, d.ic90_sup - d.substituicoes],
                fmt="none", ecolor="k", capsize=3, lw=0.8, label="IC 90% (bootstrap)")
    a0 = cfg.anos[1]
    novos = res.at["religador", f"novos_por_ano_{a0}_{base}_media"]
    ax.axhline(novos, color="#d62728", ls="--", lw=1,
               label=f"religadores novos por ano em {a0}-{base} (média {novos:.0f})")
    for _, r in d.iterrows():
        if pd.notna(r.capex_rs_mi):
            ax.text(r.ano, r.ic90_sup + 4, f"R$ {r.capex_rs_mi:.0f} mi", ha="center", fontsize=7)
    sufixo_capex = " (CAPEX com custo ilustrativo)" if d.capex_rs_mi.notna().any() else ""
    ax.set(xlabel="ano", ylabel="religadores",
           title=cfg.titulo(f"Religadores: substituições esperadas {pj_cfg['inicio']}-{pj_cfg['fim']}{sufixo_capex}"))
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(F / "04_projecao_religadores.png")
else:
    print("religador sem projeção (classe não confiável): figura 04 não gerada")

# 5. validação (religador)
if "religador" in conf:
    v = val[(val.classe == "religador") & (val.desenho == val.desenho.iloc[0])]
    aj = a["validacoes"][0]["ajuste"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    metodos = ["weibull", "taxa_constante", "idade_limite", "persistencia"]
    nomes = {"weibull": "Weibull", "taxa_constante": "taxa constante", "idade_limite": f"idade-limite {L} anos",
             "persistencia": "persistência"}
    anos = sorted(v.ano.unique())
    w = 0.16
    for i, mt in enumerate(metodos):
        d = v[v.metodo == mt].set_index("ano").reindex(anos)
        ax.bar(np.arange(len(anos)) + (i - 1.5) * w, d.previsto, width=w, label=nomes[mt])
    obs = v[v.metodo == "weibull"].set_index("ano").reindex(anos).observado
    ax.scatter(np.arange(len(anos)) + 0.45, obs, color="k", zorder=3, marker="D", label="observado")
    ax.set_xticks(np.arange(len(anos)), anos)
    ax.set(ylabel="religadores baixados",
           title=cfg.titulo(f"Validação fora da amostra (ajuste com {min(aj) + 1}-{max(aj) + 1})"))
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(F / "05_validacao.png")

# 6. qualidade do cadastro: contagem por safra, classes de comparação (MT: religador, estável, e regulador, instável)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True)
for ax, classe in zip(axes, fig_cfg.get("classes_qualidade", ["religador", "regulador"])):
    m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
    m.columns = m.columns.astype(int)
    top = m[[c for c in m.columns if c >= cfg.anos[0]]].loc[lambda d: d.index <= cfg.anos[0]]
    top = top.loc[top.max(axis=1).sort_values(ascending=False).index[:8]]
    for v_, row in top.iterrows():
        ax.plot(row.index, row.values, marker="o", ms=3, lw=1, label=str(v_))
    ax.set(title=f"{cfg.classes[classe]['nome']}: contagem por safra", xlabel="cadastro (31/12)")
    ax.legend(title="safra", fontsize=7, ncol=2)
axes[0].set_ylabel("equipamentos")
rotula(fig)
fig.tight_layout()
fig.savefig(F / "06_qualidade_cadastro.png")

# 7. acréscimos em safras antigas por baixa, em cada transição (o teste de consistência olha esta razão)
if fig_cfg.get("reversoes_por_transicao", False):
    fig, ax = plt.subplots(figsize=(8, 4))
    trs = cfg.anos[:-1]
    for classe in cfg.classes:
        m = pd.read_parquet(cfg.processed / f"matriz_{classe}.parquet")
        m.columns = m.columns.astype(int)
        r = []
        for t in trs:
            mov = C.movimentos(m, [t])
            r.append(mov.acrescimos.sum() / mov.baixas.sum() if mov.baixas.sum() else np.nan)
        ax.plot(range(len(trs)), r, marker="o", color=COR[classe], label=cfg.classes[classe]["nome"])
    ax.axhline(a["limite_reversoes"], color="k", ls="--", lw=1, label=f"limite do teste ({a['limite_reversoes']})")
    ax.set_yscale("symlog", linthresh=0.1)
    ax.set_xticks(range(len(trs)), [f"{t}→{t + 1}" for t in trs])
    ax.set(xlabel="transição entre cadastros", ylabel="acréscimos / baixas em safras antigas (escala symlog)",
           title=cfg.titulo("Acréscimos por baixa, por transição"))
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(F / "07_reversoes_por_transicao.png")
print("ok")
