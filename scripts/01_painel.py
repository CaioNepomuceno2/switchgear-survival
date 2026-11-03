"""Monta o painel de safras por classe e os diagnósticos de rastreamento do cadastro.

Saídas:
  data/processed/equipamentos.parquet   equipamento x cadastro (classe, COD_ID, safra, atributos)
  data/processed/matriz_<classe>.parquet contagem safra x cadastro
  reports/qualidade_ids.csv             estabilidade de COD_ID, DAT_IMO, meio de isolação e unidade
  reports/qualidade_pontos_religador.csv rastreamento dos pontos de religador (ID + posição)
  reports/qualidade_classes.csv         sem data, baixas, acréscimos em safras antigas (reversões)
  reports/frota_por_ano.csv             frota por classe e cadastro
"""
import json

import pandas as pd

from swsurv import cadastro as C
from swsurv.config import ROOT, Config

cfg = Config.load()
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)
anos = cfg.anos
a = cfg["analise"]

todos, qual, ids = [], [], []
for classe, spec in cfg.classes.items():
    eq = pd.concat([C.ler_classe(cfg.cache, ano, spec["camada"], spec["tuc"]) for ano in anos], ignore_index=True)
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
    qual.append({"classe": classe, "frota_2025": int((eq.ano == 2025).sum()),
                 "sem_data_2025": round(float(sd.get(2025)), 4),
                 "baixas_principal": q["baixas"], "acrescimos_principal": q["acrescimos_safras_antigas"],
                 "reversoes_principal": round(q["reversoes"], 3),
                 "baixas_com_2021": qs["baixas"], "acrescimos_com_2021": qs["acrescimos_safras_antigas"],
                 "reversoes_com_2021": round(qs["reversoes"], 3),
                 "safras_nao_monotonas": round(nm, 3),
                 "confiavel": bool(q["reversoes"] <= a["limite_reversoes"] and nm <= a["limite_nao_monotonas"])})
    ids.append(C.estabilidade_ids(cfg.cache, anos, spec["camada"], spec["tuc"]).assign(classe=classe))
    print(classe, json.dumps(qual[-1], ensure_ascii=False), flush=True)

eq = pd.concat(todos, ignore_index=True)
eq.to_parquet(cfg.processed / "equipamentos.parquet", index=False)
eq.groupby(["classe", "ano"]).size().unstack().to_csv(OUT / "frota_por_ano.csv")
pd.DataFrame(qual).to_csv(OUT / "qualidade_classes.csv", index=False)
pd.concat(ids, ignore_index=True).round(4).to_csv(OUT / "qualidade_ids.csv", index=False)

pontos = C.pontos_religador(cfg.cache, list(range(2018, 2026)))
pontos.to_csv(OUT / "qualidade_pontos_religador.csv", index=False)
print(pd.concat(ids).round(3).to_string(index=False))
print(pontos.to_string(index=False))
