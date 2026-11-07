"""Configuração por distribuidora.

Cada distribuidora tem um YAML em ``configs/`` (``premissas.yaml`` = Energisa MT, ``premissas_ems.yaml`` = Energisa MS).
A escolha vem, nesta ordem, de:

1. o argumento ``--config`` do script;
2. a variável de ambiente ``SWSURV_CONFIG``;
3. ``configs/premissas.yaml`` (padrão: Energisa MT, caminhos e resultados publicados).

Caminhos relativos (no YAML ou nas variáveis) valem a partir da raiz do projeto; caminhos absolutos são respeitados.
Chaves ausentes caem no valor de MT, para que um YAML antigo continue valendo.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PADRAO = ROOT / "configs" / "premissas.yaml"
CONFIG_ENV = "SWSURV_CONFIG"
CACHE_ENV = "SWSURV_CACHE"
ZIPS_ENV = "SWSURV_BDGD_ZIPS"

# valores de MT, usados quando o YAML não diz outra coisa
PADRAO_ZIP = "bdgd_{ano}_{item}.gdb.zip"
TIP_UNID_RELIGADOR = "32"
TOLERANCIA_PONTOS_M = 30.0
LATITUDE_REFERENCIA = -13.0


def _resolver(path: str | Path | None) -> Path:
    if path is None:
        path = os.environ.get(CONFIG_ENV, "").strip() or CONFIG_PADRAO
    p = Path(path).expanduser()
    if not p.is_absolute() and not p.exists() and (ROOT / p).exists():
        p = ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"configuração não encontrada: {path}")
    return p


def _absoluto(p: str | Path) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Config:
    raw: dict
    origem: Path | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Lê a configuração de ``path``; sem ``path``, vale ``SWSURV_CONFIG`` e depois ``configs/premissas.yaml``."""
        arquivo = _resolver(path)
        return cls(yaml.safe_load(arquivo.read_text(encoding="utf-8")), arquivo)

    # --- identificação da distribuidora -------------------------------------------------------------------
    @property
    def sigla(self) -> str:
        d = self.raw.get("distribuidora", "EMT")
        return str(d["sigla"] if isinstance(d, dict) else d)

    @property
    def cod_aneel(self) -> int | None:
        """Código ANEEL da distribuidora (405 = Energisa MT, 404 = Energisa MS); confere a coluna DIST da BDGD."""
        d = self.raw.get("cod_aneel")
        return int(d) if d is not None else None

    @property
    def nome(self) -> str:
        return self.raw.get("nome", "Energisa Mato Grosso")

    @property
    def nome_curto(self) -> str:
        return self.raw.get("nome_curto", "Energisa MT")

    @property
    def rotular_figuras(self) -> bool:
        """Acrescenta o nome da distribuidora ao título das figuras (MT não, para manter as figuras publicadas)."""
        return bool(self.raw.get("figuras", {}).get("rotular_distribuidora", False))

    def titulo(self, texto: str) -> str:
        return f"{texto} - {self.nome_curto}" if self.rotular_figuras else texto

    # --- caminhos -----------------------------------------------------------------------------------------
    @property
    def cache(self) -> Path:
        """Pasta do cache por camada (<cache>/<ano>/<CAMADA>.parquet).

        A variável de ambiente SWSURV_CACHE, se definida e não vazia, vence o `paths.cache` do YAML.
        Caminho relativo (no YAML ou na variável) vale a partir da raiz do projeto; absoluto é respeitado.
        A pasta não é criada aqui: quem grava (scripts/00_baixar_bdgd.py) cria.
        """
        env = os.environ.get(CACHE_ENV, "").strip()
        return _absoluto(env or self.raw["paths"]["cache"])

    @property
    def processed(self) -> Path:
        p = ROOT / self.raw["paths"]["processed"]
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports(self) -> Path:
        """Pasta dos CSV e figuras (padrão de MT: ``reports``). Não é criada aqui: quem grava cria."""
        return _absoluto(self.raw["paths"].get("reports", "reports"))

    @property
    def figuras(self) -> Path:
        return self.reports / "figures"

    def zips_locais(self, argumento: str | Path | None = None) -> Path | None:
        """Pasta com os zips da BDGD já baixados (``bdgd_<ano>_<item>.gdb.zip``), ou None para baixar do ArcGIS.

        Vale, nesta ordem, o argumento ``--zips``, a variável ``SWSURV_BDGD_ZIPS`` e ``bdgd.zips_locais`` do YAML.
        Os zips só são lidos, nunca alterados.
        """
        valor = argumento or os.environ.get(ZIPS_ENV, "").strip() or self.raw.get("bdgd", {}).get("zips_locais")
        return _absoluto(valor) if valor else None

    @property
    def padrao_zip(self) -> str:
        return self.raw.get("bdgd", {}).get("padrao_zip", PADRAO_ZIP)

    # --- cadastro -----------------------------------------------------------------------------------------
    @property
    def classes(self) -> dict:
        return self.raw["classes"]

    @property
    def anos(self) -> list[int]:
        return list(self.raw["bdgd"]["anos_com_data"])

    @property
    def ano_base(self) -> int:
        """Último cadastro com data válida: a frota que a projeção envelhece."""
        return max(self.anos)

    @property
    def anos_snapshots(self) -> list[int]:
        """Todos os cadastros (inclui os sem data útil), usados no rastreamento dos pontos de religador."""
        return sorted(int(a) for a in self.raw["bdgd"]["snapshots"])

    @property
    def pontos(self) -> dict:
        """Parâmetros do rastreamento dos pontos de religador (camada UNSEMT)."""
        p = self.raw.get("pontos", {})
        return {"tip_unid": str(p.get("tip_unid_religador", TIP_UNID_RELIGADOR)),
                "tol_m": float(p.get("tolerancia_m", TOLERANCIA_PONTOS_M)),
                "lat_ref": float(p.get("lat_ref_graus", LATITUDE_REFERENCIA))}

    def __getitem__(self, k):
        return self.raw[k]


def parser(descricao: str) -> argparse.ArgumentParser:
    """Parser dos scripts: já traz ``--config``. Os scripts acrescentam os próprios argumentos."""
    ap = argparse.ArgumentParser(description=descricao, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None,
                    help=f"YAML da distribuidora (padrão: ${CONFIG_ENV} ou configs/premissas.yaml)")
    return ap


def carregar(descricao: str, argv: list[str] | None = None) -> Config:
    """Atalho para scripts sem outros argumentos: lê ``--config`` e devolve a configuração."""
    return Config.load(parser(descricao).parse_args(argv).config)
