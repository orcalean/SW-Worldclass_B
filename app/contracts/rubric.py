"""Rubric + scoring policy contracts. Rubrics are data: adding checks or cores needs no code."""
from __future__ import annotations

from pydantic import BaseModel, Field

LEVELS = ("L1", "L2", "L3")


class Check(BaseModel):
    benchmark_id: str = Field(..., description="e.g. Q01-3-01")
    subcategory_id: str
    requirement: str
    criteria: dict[str, str] = Field(..., description="Level -> criterion text (L1/L2/L3)")
    evidence_inputs: str | None = None
    primary_source: str | None = None
    supporting_source: str | None = None
    notes: str | None = None


class Subcategory(BaseModel):
    id: str
    name: str
    purpose: str | None = None
    checks: list[Check]


class Core(BaseModel):
    id: str = Field(..., description="e.g. Q.core1")
    dimension: str = Field(..., description="S | Q | D | C | M | E")
    number: int
    name: str
    question: str | None = None
    boundary: str | None = None
    level_roles: dict[str, str] = Field(default_factory=dict)
    subcategories: list[Subcategory]
    version: str

    def checks(self) -> list[Check]:
        return [c for s in self.subcategories for c in s.checks]


class ScoringPolicy(BaseModel):
    version: str
    benchmark: float = 90.0
    verdict_points: dict[str, float] = Field(
        default_factory=lambda: {"met": 1.0, "partial": 0.5, "gap": 0.0}
    )
    check_weights: dict[str, float] = Field(default_factory=dict, description="benchmark_id -> weight (default 1)")
    subcategory_weights: dict[str, float] = Field(default_factory=dict, description="subcategory_id -> weight")
    core_weights: dict[str, float] = Field(default_factory=dict, description="core_id -> weight")
    blocking_checks: list[str] = Field(default_factory=list, description="A gap here blocks 'Benchmark verified'")
    require_evidence_levels: list[str] = Field(
        default_factory=lambda: ["L2", "L3"],
        description="Levels whose evidence must be present (not evidence_missing) for verification",
    )
    na_requires_reason: bool = True
    low_confidence_threshold: float = 0.6
