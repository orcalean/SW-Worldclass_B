"""Evaluate an SOPDocument end-to-end: assess (LLM) -> score (deterministic) -> overlay + improvements."""
from __future__ import annotations

import hashlib
import json

from app.contracts.evaluation import EngineInfo, EvaluationResult, Usage
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.evaluation.assessor import Assessor
from app.evaluation.prompts import PROMPT_VERSION
from app.llm.client import LLM, CallUsage
from app.rubric.registry import Catalogue
from app.scoring import improvements as imp
from app.scoring.scorer import score

ENGINE_VERSION = "0.1.2"


def cache_key(doc: SOPDocument, evidence: list[EvidenceItem], catalogue: Catalogue, llm_name: str, model: str) -> str:
    payload = {
        "doc": doc.model_dump(mode="json", by_alias=True, exclude={"source"}),
        "evidence": sorted((e.model_dump(mode="json") for e in evidence), key=lambda e: e["id"]),
        "rubrics": sorted(f"{c.id}@{c.version}" for c in catalogue.assessed_cores()),
        "policy": catalogue.policy.version, "prompt": PROMPT_VERSION, "engine": ENGINE_VERSION,
        "llm": llm_name, "model": model,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def evaluate(doc: SOPDocument, evidence: list[EvidenceItem], catalogue: Catalogue, llm: LLM,
                   model: str, effort: str = "medium") -> EvaluationResult:
    usage = CallUsage()
    raw = await Assessor(llm, model, effort, catalogue.policy.low_confidence_threshold).assess(
        doc, evidence, catalogue.assessed_cores(), usage)
    overall, gate, dims, results = score(catalogue, raw)
    return EvaluationResult(
        engine=EngineInfo(
            engine_version=ENGINE_VERSION,
            rubric_versions={c.id: c.version for c in catalogue.assessed_cores()},
            policy_version=catalogue.policy.version, prompt_version=PROMPT_VERSION,
            models={"evaluation": f"{llm.name}:{model}"},
        ),
        overall=overall, gate=gate, dimensions=dims,
        work_elements=imp.overlay(doc, results),
        improvements=imp.improvements(catalogue, results),
        usage=Usage(llm_calls=usage.calls, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens, cost_usd=round(usage.cost_usd, 4)),
    )
