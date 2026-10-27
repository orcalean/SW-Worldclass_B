"""Loads the rubric catalogue: SQDCME dimensions, their cores (assessed or placeholder) and the policy."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.contracts.rubric import Core, ScoringPolicy

RUBRIC_DIR = Path(__file__).resolve().parents[2] / "rubrics"


@dataclass(frozen=True)
class CoreSlot:
    dimension: str
    number: int
    name: str
    core: Core | None  # None = placeholder, shown as "Not assessed"


@dataclass(frozen=True)
class DimensionSlot:
    key: str
    name: str
    cores: tuple[CoreSlot, ...]


@dataclass(frozen=True)
class Catalogue:
    dimensions: tuple[DimensionSlot, ...]
    policy: ScoringPolicy

    def assessed_cores(self) -> list[Core]:
        return [c.core for d in self.dimensions for c in d.cores if c.core is not None]

    def check(self, benchmark_id: str):
        for core in self.assessed_cores():
            for chk in core.checks():
                if chk.benchmark_id == benchmark_id:
                    return chk
        return None


@lru_cache(maxsize=4)
def load_catalogue(rubric_dir: Path = RUBRIC_DIR, policy_file: str = "policy@1.0.json") -> Catalogue:
    spec = json.loads((rubric_dir / "dimensions.json").read_text())
    dims = []
    for d in spec["dimensions"]:
        slots = []
        for c in d["cores"]:
            core = None
            if c.get("file"):
                core = Core.model_validate_json((rubric_dir / c["file"]).read_text())
            slots.append(CoreSlot(d["key"], c["number"], c["name"], core))
        dims.append(DimensionSlot(d["key"], d["name"], tuple(slots)))
    policy = ScoringPolicy.model_validate_json((rubric_dir / policy_file).read_text())
    return Catalogue(tuple(dims), policy)
