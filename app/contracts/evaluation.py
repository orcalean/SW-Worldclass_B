"""EvaluationResult: the output contract of /v1/evaluate. Drives every panel of the audit UI."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    met = "met"
    partial = "partial"
    gap = "gap"
    evidence_missing = "evidence_missing"
    not_applicable = "not_applicable"


class EvidenceRef(BaseModel):
    work_element_id: str | None = None
    quote: str | None = Field(None, description="Verbatim text from the SOP/evidence supporting the verdict")
    page: int | None = None
    source: str = Field("sop", description="sop | evidence:<id>")
    verified: bool = Field(False, description="Quote was found in the source text by the verifier")


class CheckResult(BaseModel):
    benchmark_id: str
    subcategory_id: str
    requirement: str
    level: str
    verdict: Verdict
    rationale: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0, le=1)
    work_element_ids: list[str] = Field(default_factory=list)
    root_of: str | None = Field(None, description="benchmark_id of the root finding this is a consequence of")
    blocking: bool = False
    suggested_fix: str | None = None


class LevelScore(BaseModel):
    level: str
    score: float | None = Field(None, description="0-100, null when nothing scoreable")
    scored: int = 0
    evidence_missing: int = 0
    not_applicable: int = 0
    total: int = 0
    evidence_completeness: float | None = Field(None, description="% of applicable checks with evidence")


class SubcategoryResult(BaseModel):
    id: str
    name: str
    levels: dict[str, LevelScore]
    checks: list[CheckResult]


class CoreResult(BaseModel):
    id: str
    number: int
    name: str
    assessed: bool
    status: str = Field(..., description="verified | gap | evidence | not_assessed")
    levels: dict[str, LevelScore] = Field(default_factory=dict)
    subcategories: list[SubcategoryResult] = Field(default_factory=list)


class DimensionResult(BaseModel):
    key: str
    name: str
    assessed: bool
    score: float | None = None
    status: str
    summary: str
    cores: list[CoreResult] = Field(default_factory=list)


class Gate(BaseModel):
    status: str = Field(..., description="passed | blocked")
    blocking: list[str] = Field(default_factory=list, description="benchmark_ids with blocking gaps")
    reasons: list[str] = Field(default_factory=list)


class Overall(BaseModel):
    score: float | None
    benchmark: float
    status: str = Field(..., description="benchmark_verified | not_verified")
    reason: str
    evidence_completeness: dict[str, float | None] = Field(default_factory=dict)


class WorkElementOverlay(BaseModel):
    work_element_id: str
    seq: int
    title: str
    dimensions: list[str] = Field(default_factory=list)
    status: str = Field(..., description="verified | gap | blocked | evidence | no_findings")
    issues: list[str] = Field(default_factory=list, description="Short chip labels")
    check_ids: list[str] = Field(default_factory=list)


class Improvement(BaseModel):
    priority: str = Field(..., description="must_fix | evidence | benchmark")
    title: str
    action: str
    owner_role: str
    check_ids: list[str]
    work_element_ids: list[str] = Field(default_factory=list)
    blocks_release: bool = False


class EngineInfo(BaseModel):
    engine_version: str
    rubric_versions: dict[str, str]
    policy_version: str
    prompt_version: str
    models: dict[str, str]


class Usage(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    cached_result: bool = False


class EvaluationResult(BaseModel):
    schema_version: str = "evaluation-result/1.0"
    engine: EngineInfo
    overall: Overall
    gate: Gate
    dimensions: list[DimensionResult]
    work_elements: list[WorkElementOverlay]
    improvements: list[Improvement]
    usage: Usage = Field(default_factory=Usage)
