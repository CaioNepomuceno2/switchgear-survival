from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    raw: dict

    @classmethod
    def load(cls, path: str | Path = ROOT / "configs" / "premissas.yaml") -> Config:
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    @property
    def cache(self) -> Path:
        return Path(self.raw["paths"]["cache"])

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
