"""Monta o painel de safras por classe e os diagnósticos de rastreamento do cadastro.

Saídas (pastas da configuração; em MT, data/processed e reports):
  <processed>/equipamentos.parquet   equipamento x cadastro (classe, COD_ID, safra, atributos)
  <processed>/matriz_<classe>.parquet contagem safra x cadastro
  <reports>/qualidade_ids.csv             estabilidade de COD_ID, DAT_IMO, meio de isolação e unidade
  <reports>/qualidade_pontos_religador.csv rastreamento dos pontos de religador (ID + posição)
  <reports>/qualidade_classes.csv         sem data, baixas, acréscimos em safras antigas (reversões)
  <reports>/frota_por_ano.csv             frota por classe e cadastro

Outra distribuidora: --config configs/premissas_ems.yaml (ou SWSURV_CONFIG).
"""
import json

import pandas as pd

from swsurv import cadastro as C
from swsurv.config import carregar

cfg = carregar(__doc__)
OUT = cfg.reports
OUT.mkdir(parents=True, exist_ok=True)
anos = cfg.anos
base = cfg.ano_base
a = cfg["analise"]
suf = a.get("sufixo_sensibilidade", "com_2021")  # nome das colunas da janela de sensibilidade

todos, qual, ids = [], [], []
for classe, spec in cfg.classes.items():
    eq = pd.concat([C.ler_classe(cfg.cache, ano, spec["camada"], spec["tuc"], cfg.cod_aneel) for ano in anos],
                   ignore_index=True)
    eq["classe"] = classe
    todos.append(eq)
    m = C.matriz_safras(eq)
    m.to_parquet(cfg.processed / f"matriz_{classe}.parquet")
    mov_p = C.movimentos(m, a["transicoes_principal"])
    mov_s = C.movimentos(m, a["transicoes_sensibilidade"])
    q = C.qualidade_classe(mov_p)
    qs = C.qualidade_classe(mov_s)
    sd = C.sem_data(eq)
    janela = sorted({t for t in a["transicoes_principal"]} | {t + 1 for t in a["transicoes_principal"]})
    nm = C.safras_nao_monotonas(m, janela)
    qual.append({"classe": classe, f"frota_{base}": int((eq.ano == base).sum()),
                 f"sem_data_{base}": round(float(sd.get(base)), 4),
                 "baixas_principal": q["baixas"], "acrescimos_principal": q["acrescimos_safras_antigas"],
                 "reversoes_principal": round(q["reversoes"], 3),
                 f"baixas_{suf}": qs["baixas"], f"acrescimos_{suf}": qs["acrescimos_safras_antigas"],
                 f"reversoes_{suf}": round(qs["reversoes"], 3),
                 "safras_nao_monotonas": round(nm, 3),
                 "confiavel": bool(q["reversoes"] <= a["limite_reversoes"] and nm <= a["limite_nao_monotonas"])})
    ids.append(C.estabilidade_ids(cfg.cache, anos, spec["camada"], spec["tuc"], cfg.cod_aneel).assign(classe=classe))
    print(classe, json.dumps(qual[-1], ensure_ascii=False), flush=True)

eq = pd.concat(todos, ignore_index=True)
eq.to_parquet(cfg.processed / "equipamentos.parquet", index=False)
eq.groupby(["classe", "ano"]).size().unstack().to_csv(OUT / "frota_por_ano.csv")
pd.DataFrame(qual).to_csv(OUT / "qualidade_classes.csv", index=False)
pd.concat(ids, ignore_index=True).round(4).to_csv(OUT / "qualidade_ids.csv", index=False)

pontos = C.pontos_religador(cfg.cache, cfg.anos_snapshots, **cfg.pontos)
pontos.to_csv(OUT / "qualidade_pontos_religador.csv", index=False)
print(pd.concat(ids).round(3).to_string(index=False))
print(pontos.to_string(index=False))
