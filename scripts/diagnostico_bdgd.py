"""Diagnóstico dos dados da BDGD de uma distribuidora, ANTES de qualquer estimativa de vida.

Mede o que decide a configuração (anos com data, classes por TUC, limiares, janelas), sem ajustar nenhuma curva:
  1. linhas repetidas (count(*) contra count(distinct *)) em todas as camadas lidas, por cadastro;
  2. camadas e colunas por cadastro (mudança de modelo);
  3. TUC por cadastro e TUC contra o TIP_UNID da unidade a que o equipamento pertence;
  4. qualidade de DAT_IMO por classe e cadastro (vazia, data-padrão, antes de 1950, no futuro, válida);
  5. qualidade das transições (acréscimos em safras antigas contra baixas) por classe, as safras principais de
     cada cadastro e o "vai e volta" das datas (mesmo equipamento, mesma safra antes e depois, outra no meio);
  6. janelas candidatas de ajuste, com os indicadores de consistência;
  7. pontos de religador (UNSEMT): extensão geográfica e latitude de referência;
  8. nível de tensão (GRU_TEN) de cada TUC.
Entrada: o cache por camada (scripts/00_baixar_bdgd.py). Saída: <reports>/diagnostico/*.csv

    python scripts/diagnostico_bdgd.py --config configs/premissas_ems.yaml
"""
import pandas as pd

from swsurv import cadastro as C
from swsurv.bdgd import CAMADAS
from swsurv.config import carregar

cfg = carregar(__doc__)
OUT = cfg.reports / "diagnostico"
OUT.mkdir(parents=True, exist_ok=True)
anos = cfg.anos_snapshots
a = cfg.raw.get("analise", {})


def ler(ano: int, camada: str) -> pd.DataFrame:
    return pd.read_parquet(cfg.cache / str(ano) / f"{camada}.parquet")


def salva(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False)
    print(f"--- {nome} ({len(df)} linhas)")
    print(df.to_string(index=False, max_rows=60))


# 1 e 2. linhas repetidas, distribuidora (DIST) e colunas -------------------------------------------------
rep, esq, anterior = [], [], {}
for camada in CAMADAS:
    for ano in anos:
        df = ler(ano, camada)
        n, nd = len(df), len(df.drop_duplicates())
        rep.append({"camada": camada, "ano": ano, "linhas": n, "linhas_distintas": nd, "repetidas": n - nd,
                    "pct_repetidas": round(100 * (n - nd) / n, 4) if n else 0.0,
                    "cod_id_distintos": int(df["COD_ID"].nunique()),
                    "linhas_com_cod_id_repetido": int(df["COD_ID"].duplicated(keep=False).sum()),
                    "dist": ",".join(sorted(df["DIST"].dropna().astype(str).unique())) if "DIST" in df else ""})
        cols = df.columns.tolist()
        esq.append({"camada": camada, "ano": ano, "colunas": len(cols),
                    "novas": " ".join(c for c in cols if c not in anterior.get(camada, cols)),
                    "removidas": " ".join(c for c in anterior.get(camada, cols) if c not in cols)})
        anterior[camada] = cols
salva(pd.DataFrame(rep), "repetidas_camadas.csv")
salva(pd.DataFrame(esq), "esquema_camadas.csv")

# 3. TUC por cadastro e TUC contra o tipo da unidade -------------------------------------------------------
tuc_ano, tuc_tip = [], []
for camada, unid, chave_ano in [("EQSE", "UNSEMT", "UN_SE"), ("EQRE", "UNREMT", "UN_RE")]:
    for ano in anos:
        e = ler(ano, camada)
        e["TUC"] = e["TUC"].astype("string").str.strip()
        for tuc, n in e["TUC"].value_counts(dropna=False).items():
            tuc_ano.append({"camada": camada, "ano": ano, "tuc": tuc, "equipamentos": int(n)})
        u = ler(ano, unid)[["COD_ID", "PAC_1", "TIP_UNID"]]
        if chave_ano in e:  # modelo V10/V11: o equipamento aponta para a unidade
            j = e.merge(u[["COD_ID", "TIP_UNID"]].rename(columns={"COD_ID": chave_ano}), on=chave_ano, how="left")
            chave = chave_ano
        else:  # modelo M10: o vínculo é pelo PAC_1
            j = e.merge(u[["PAC_1", "TIP_UNID"]].drop_duplicates("PAC_1"), on="PAC_1", how="left")
            chave = "PAC_1"
        assert len(j) == len(e), "o vínculo multiplicou linhas"
        g = j.assign(TIP_UNID=j["TIP_UNID"].astype("string").str.strip().fillna("sem unidade")).groupby(
            ["TUC", "TIP_UNID"]).size()
        for (tuc, tip), n in g.items():
            tuc_tip.append({"camada": camada, "ano": ano, "vinculo": chave, "tuc": tuc, "tip_unid": tip,
                            "equipamentos": int(n)})
salva(pd.DataFrame(tuc_ano), "tuc_por_ano.csv")
salva(pd.DataFrame(tuc_tip), "tuc_x_tip_unid.csv")

# 8. nível de tensão (GRU_TEN, só no modelo V10/V11) de cada TUC
tensao = []
for camada in ("EQSE", "EQRE"):
    for ano in anos:
        e = ler(ano, camada)
        if "GRU_TEN" not in e:
            continue
        e["TUC"] = e["TUC"].astype("string").str.strip()
        for (tuc, gru), n in e.groupby(["TUC", e["GRU_TEN"].astype("string").str.strip()]).size().items():
            tensao.append({"camada": camada, "ano": ano, "tuc": tuc, "gru_ten": gru, "equipamentos": int(n)})
salva(pd.DataFrame(tensao), "tuc_x_tensao.csv")

# 4. qualidade de DAT_IMO por classe (e pelos TUC fora das classes) e cadastro -----------------------------
linhas = []
for ano in anos:
    partes = {}
    for classe, spec in cfg.classes.items():
        e = ler(ano, spec["camada"])
        e["TUC"] = e["TUC"].astype("string").str.strip()
        partes[classe] = e[e["TUC"] == spec["tuc"]]
    for camada in ("EQSE", "EQRE"):
        e = ler(ano, camada)
        e["TUC"] = e["TUC"].astype("string").str.strip()
        fora = e[~e["TUC"].isin({s["tuc"] for s in cfg.classes.values() if s["camada"] == camada})]
        if len(fora):
            partes[f"fora_das_classes_{camada}"] = fora
    for nome, e in partes.items():
        s = e["DAT_IMO"].astype("string").str.strip()
        vazio = s.isna() | (s == "") | (s == "0")
        v = pd.to_numeric(s.str[-4:], errors="coerce")
        valido = (~vazio) & v.between(C.ANO_MIN_SAFRA, ano)
        n = len(e)
        top = s[~vazio].value_counts()
        linhas.append({"classe": nome, "ano": ano, "equipamentos": n,
                       "pct_vazia_ou_0": round(100 * vazio.mean(), 2) if n else None,
                       "pct_01_01_1920": round(100 * (s == "01/01/1920").mean(), 2) if n else None,
                       "pct_antes_1950": round(100 * ((~vazio) & (v < C.ANO_MIN_SAFRA)).mean(), 2) if n else None,
                       "pct_no_futuro": round(100 * ((~vazio) & (v > ano)).mean(), 2) if n else None,
                       "pct_valida": round(100 * valido.mean(), 2) if n else None,
                       "validos": int(valido.sum()),
                       "data_mais_comum": top.index[0] if len(top) else "",
                       "pct_data_mais_comum": round(100 * top.iloc[0] / n, 2) if len(top) else None,
                       "safra_min": int(v[valido].min()) if valido.any() else None,
                       "safra_max": int(v[valido].max()) if valido.any() else None,
                       "safras_distintas": int(v[valido].nunique())})
salva(pd.DataFrame(linhas), "dat_imo_qualidade.csv")

# 5. qualidade das transições (todas as que existem entre os cadastros) -----------------------------------------
cod = cfg.cod_aneel
trans, matrizes = [], {}
for classe, spec in cfg.classes.items():
    eq = pd.concat([C.ler_classe(cfg.cache, ano, spec["camada"], spec["tuc"], cod) for ano in anos],
                   ignore_index=True)
    m = C.matriz_safras(eq)
    matrizes[classe] = m
    tot = eq.groupby("ano").size()
    dat = eq.dropna(subset=["safra"]).groupby("ano").size()
    for t in anos[:-1]:
        mov = C.movimentos(m, [t])
        trans.append({"classe": classe, "transicao": f"{t}->{t + 1}",
                      "equipamentos_t": int(tot.get(t, 0)), "datados_t": int(dat.get(t, 0)),
                      "equipamentos_t1": int(tot.get(t + 1, 0)), "datados_t1": int(dat.get(t + 1, 0)),
                      "expostos": int(mov.expostos.sum()), "baixas": int(mov.baixas.sum()),
                      "acrescimos": int(mov.acrescimos.sum()),
                      "reversoes": round(mov.acrescimos.sum() / mov.baixas.sum(), 3) if mov.baixas.sum() else None})
salva(pd.DataFrame(trans), "transicoes.csv")

principais, vaivem = [], []
for classe, spec in cfg.classes.items():
    m = matrizes[classe]
    for v in m.max(axis=1).sort_values(ascending=False).index[:10]:
        for ano in m.columns:
            principais.append({"classe": classe, "safra": int(v), "ano": int(ano), "equipamentos": int(m.at[v, ano])})
    eq = pd.concat([C.ler_classe(cfg.cache, ano, spec["camada"], spec["tuc"], cod) for ano in anos], ignore_index=True)
    s_id = eq.pivot_table(index="COD_ID", columns="ano", values="safra", aggfunc="first")
    for t in [x for x in sorted(m.columns) if x - 1 in m.columns and x + 1 in m.columns]:
        tres = s_id[[t - 1, t, t + 1]].dropna()
        iguais = tres[tres[t - 1] == tres[t + 1]]
        diferente = int((iguais[t] != iguais[t - 1]).sum())
        vaivem.append({"classe": classe, "ano_do_meio": t, "ids_nos_3_cadastros": len(tres),
                       "mesma_safra_antes_e_depois": len(iguais), "outra_safra_no_meio": diferente,
                       "pct_outra_no_meio": round(100 * diferente / len(iguais), 2) if len(iguais) else None})
salva(pd.DataFrame(principais), "safras_principais.csv")
salva(pd.DataFrame(vaivem), "vai_e_volta_das_datas.csv")

# 6. janelas candidatas: indicadores de consistência (sem ajustar curva nenhuma) -----------------------------------
lim_rev, lim_nm = a.get("limite_reversoes", 0.25), a.get("limite_nao_monotonas", 0.10)
cand = []
ultimo = anos[-1] - 1  # última transição: t -> ultimo + 1
for inicio in [x for x in anos if x < ultimo]:
    janela = list(range(inicio, ultimo + 1))
    anos_j = sorted({t for t in janela} | {t + 1 for t in janela})
    for classe, m in matrizes.items():
        mov = C.movimentos(m, janela)
        if mov.empty:
            continue
        q = C.qualidade_classe(mov)
        det = C.safras_nao_monotonas_detalhe(m, anos_j)
        nm = C.safras_nao_monotonas(m, anos_j)
        cand.append({"classe": classe, "transicoes": f"{janela[0]}->{janela[-1] + 1}", "n_transicoes": len(janela),
                     "baixas": q["baixas"], "acrescimos": q["acrescimos_safras_antigas"],
                     "reversoes": round(q["reversoes"], 3) if q["baixas"] else None,
                     "safras_elegiveis": len(det), "safras_que_voltam_a_subir": int(det.sum()),
                     "safras_nao_monotonas": round(nm, 3) if pd.notna(nm) else None,
                     "passa_limites_de_mt": bool(q["baixas"] and q["reversoes"] <= lim_rev and nm <= lim_nm)})
salva(pd.DataFrame(cand), "janelas_candidatas.csv")

# 7. pontos de religador: extensão e latitude de referência -----------------------------------------------------
tip = cfg.pontos["tip_unid"]
pts = []
for ano in anos:
    u = ler(ano, "UNSEMT")
    u = u[u["TIP_UNID"].astype("string").str.strip() == tip]
    ok = u.dropna(subset=["lon", "lat"])
    pts.append({"ano": ano, "pontos_tip_unid": len(u), "com_coordenada": len(ok),
                "lon_p01": round(ok.lon.quantile(0.01), 3), "lon_mediana": round(ok.lon.median(), 3),
                "lon_p99": round(ok.lon.quantile(0.99), 3), "lat_p01": round(ok.lat.quantile(0.01), 3),
                "lat_mediana": round(ok.lat.median(), 3), "lat_p99": round(ok.lat.quantile(0.99), 3)})
salva(pd.DataFrame(pts), "pontos_religador.csv")
