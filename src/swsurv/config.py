from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE_ENV = "SWSURV_CACHE"


@dataclass(frozen=True)
class Config:
    raw: dict

    @classmethod
    def load(cls, path: str | Path = ROOT / "configs" / "premissas.yaml") -> Config:
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    @property
    def cache(self) -> Path:
        """Pasta do cache por camada (<cache>/<ano>/<CAMADA>.parquet).

        A variável de ambiente SWSURV_CACHE, se definida e não vazia, vence o `paths.cache` do YAML.
        Caminho relativo (no YAML ou na variável) vale a partir da raiz do projeto; absoluto é respeitado.
        A pasta não é criada aqui: quem grava (scripts/00_baixar_bdgd.py) cria.
        """
        env = os.environ.get(CACHE_ENV, "").strip()
        p = Path(env or self.raw["paths"]["cache"]).expanduser()
        return p if p.is_absolute() else ROOT / p

    @property
    def processed(self) -> Path:
        p = ROOT / self.raw["paths"]["processed"]
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def classes(self) -> dict:
        return self.raw["classes"]

    @property
    def anos(self) -> list[int]:
        return list(self.raw["bdgd"]["anos_com_data"])

    def __getitem__(self, k):
        return self.raw[k]
