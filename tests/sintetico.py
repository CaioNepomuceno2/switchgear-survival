"""Cache sintético minúsculo (Parquet por camada e ano, como o cache real) para os testes de ponta a ponta.

Gera EQSE (religador 345, disjuntor 210, chave 160), EQRE (regulador 340) e UNSEMT (pontos) para 2018-2025.
Religador e disjuntor seguem vidas de Weibull (a contagem por safra só cai); chave e regulador têm a data de
imobilização sorteada de novo a cada cadastro (a contagem por safra oscila, como nas classes que o teste de
consistência reprova). Com `todas_inconsistentes=True` até religador e disjuntor oscilam: é o caso de MS.
Nada aqui lê rede nem a BDGD.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ANOS = list(range(2018, 2026))
ANOS_COM_DATA = list(range(2020, 2026))
CLASSES = {"religador": ("EQSE", "345", 2.5, 25.0, 60), "disjuntor": ("EQSE", "210", 2.0, 30.0, 30)}


def _vivos(rng, safras, n_por_safra, beta, eta):
    """Unidades com safra e fim de vida Weibull (instalação no meio do ano de imobilização)."""
    linhas = []
    for v in safras:
        fim = v + 0.5 + eta * rng.weibull(beta, n_por_safra)
        linhas += [{"safra": v, "fim": f} for f in fim]
    return pd.DataFrame(linhas)


def gerar_cache(cache: Path, cod_aneel: int = 405, todas_inconsistentes: bool = False, seed: int = 5,
                lon0: float = -56.0, lat0: float = -13.0) -> None:
    """Escreve <cache>/<ano>/{EQSE,EQRE,UNSEMT,UNREMT}.parquet para 2018-2025."""
    rng = np.random.default_rng(seed)
    safras = range(1990, 2026)
    pop = {}
    for classe, (camada, tuc, beta, eta, n) in CLASSES.items():
        u = _vivos(rng, safras, n, beta, eta)
        u["COD_ID"] = [f"{tuc}-{i:05d}" for i in range(len(u))]
        pop[classe] = u
    n_chave, n_reg = 2500, 400
    chave = pd.DataFrame({"COD_ID": [f"160-{i:05d}" for i in range(n_chave)]})
    reg = pd.DataFrame({"COD_ID": [f"340-{i:05d}" for i in range(n_reg)]})
    religadores = pop["religador"]
    pontos = pd.DataFrame({"lon": lon0 + rng.uniform(-1, 1, len(religadores)),
                           "lat": lat0 + rng.uniform(-1, 1, len(religadores))}, index=religadores.COD_ID)

    for ano in ANOS:
        eqse, unsemt = [], []
        for classe, (camada, tuc, _, _, _) in CLASSES.items():
            u = pop[classe]
            vivos = u[(u.safra <= ano) & (u.fim > ano)].copy()
            if todas_inconsistentes:  # data de imobilização sorteada de novo a cada cadastro
                vivos["safra"] = rng.integers(1990, ano + 1, len(vivos))
            vivos["DAT_IMO"] = ("15/06/" + vivos.safra.astype(str)) if ano >= 2020 else "01/01/1920"
            eqse.append(pd.DataFrame({"COD_ID": vivos.COD_ID, "DIST": cod_aneel, "TUC": tuc,
                                      "DAT_IMO": vivos.DAT_IMO, "MEI_ISO": "VC" if classe == "religador" else "GA",
                                      "UN_SE": "U" + vivos.COD_ID}))
        ch = chave.copy()
        ch["safra"] = rng.integers(1990, ano + 1, len(ch))
        eqse.append(pd.DataFrame({"COD_ID": ch.COD_ID, "DIST": cod_aneel, "TUC": "160",
                                  "DAT_IMO": ("20/03/" + ch.safra.astype(str)) if ano >= 2020 else "01/01/1920",
                                  "MEI_ISO": "SE", "UN_SE": "U" + ch.COD_ID}))
        rg = reg.copy()
        rg["safra"] = rng.integers(1990, ano + 1, len(rg))
        eqre = pd.DataFrame({"COD_ID": rg.COD_ID, "DIST": cod_aneel, "TUC": "340",
                             "DAT_IMO": ("10/10/" + rg.safra.astype(str)) if ano >= 2020 else "01/01/1920",
                             "UN_RE": "U" + rg.COD_ID})
        rel_ano = pd.concat(eqse)
        rel_ano = rel_ano[rel_ano.TUC == "345"]
        pts = pontos.loc[rel_ano.COD_ID]
        unsemt = pd.DataFrame({"COD_ID": "U" + rel_ano.COD_ID.to_numpy(), "DIST": cod_aneel, "TIP_UNID": "32",
                               "lon": pts.lon.to_numpy(), "lat": pts.lat.to_numpy()})
        unsemt = pd.concat([unsemt, pd.DataFrame({"COD_ID": ["F1", "F2"], "DIST": cod_aneel, "TIP_UNID": "22",
                                                  "lon": [lon0, lon0 + 0.1], "lat": [lat0, lat0]})])
        d = Path(cache) / str(ano)
        d.mkdir(parents=True, exist_ok=True)
        pd.concat(eqse, ignore_index=True).to_parquet(d / "EQSE.parquet", index=False)
        eqre.to_parquet(d / "EQRE.parquet", index=False)
        unsemt.to_parquet(d / "UNSEMT.parquet", index=False)
