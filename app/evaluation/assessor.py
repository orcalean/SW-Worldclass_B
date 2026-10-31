"""Module B: turn (SOPDocument, evidence, rubric) into raw per-check verdicts. LLM used here; no scoring here.

Cost/reliability design:
- one call per subcategory; system + SOP (+ evidence) form a cached prefix shared by all calls
- the first call runs alone to write the cache, the rest run concurrently and read it
- levels without uploaded evidence are resolved to evidence_missing in code (no LLM call)
- every verdict is validated: unknown ids dropped, missing checks retried once, quotes verified
"""
from __future__ import annotations

import asyncio
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.evaluation import CheckResult, EvidenceRef, Verdict
from app.contracts.evidence import EvidenceItem
from app.contracts.rubric import Core, Subcategory
from app.contracts.sop import SOPDocument
from app.evaluation import prompts
from app.evaluation.verifier import SourceIndex
from app.llm.client import LLM, CallUsage, LLMError, Request


class LLMCheck(BaseModel):
    benchmark_id: str
    level: Literal["L1", "L2", "L3"]
    verdict: Literal["met", "partial", "gap", "evidence_missing", "not_applicable"]
    rationale: str
    quotes: list[str] = Field(default_factory=list)
    work_element_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    root_of: str | None = None
    suggested_fix: str | None = None
    needs_l3: bool = False


class SubcategoryAssessment(BaseModel):
    checks: list[LLMCheck]


# Structured output occasionally leaks JSON punctuation into the end of a string ('…the rule.“}, {').
_JSON_TAIL = re.compile(r'\s*["“”]\s*[}\]]\s*(,\s*[{\[]\s*)?["“”]?\s*$')


def clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = _JSON_TAIL.sub("", s.strip()).strip()
    return s or None


class Assessor:
    def __init__(self, llm: LLM, model: str, effort: str = "medium", low_confidence: float = 0.6):
        self.llm = llm
        self.model = model
        self.effort = effort
        self.low_confidence = low_confidence

    async def assess(self, doc: SOPDocument, evidence: list[EvidenceItem], cores: list[Core],
                     usage: CallUsage) -> list[CheckResult]:
        levels = ["L1"] + [lv for lv in ("L2", "L3") if any(e.level == lv for e in evidence)]
        shared = [prompts.sop_block(doc)]
        if (eb := prompts.evidence_block(evidence)) is not None:
            shared.append(eb)
        sources = {"L1": SourceIndex(doc.all_text())}
        for lv in ("L2", "L3"):
            sources[lv] = SourceIndex("\n".join(filter(None, (x for e in evidence if e.level == lv
                                                               for x in (e.title, e.text, e.description)))))
        we_ids = {w.id for w in doc.work_elements}

        jobs = [(core, sub) for core in cores for sub in core.subcategories]
        results: list[CheckResult] = []
        if jobs:
            first = await self._subcategory(jobs[0][0], jobs[0][1], levels, shared, sources, we_ids, usage)
            rest = await asyncio.gather(*(self._subcategory(c, s, levels, shared, sources, we_ids, usage)
                                          for c, s in jobs[1:]))
            for part in [first, *rest]:
                results.extend(part)

        # Levels with no uploaded evidence: deterministic, no LLM.
        for core in cores:
            for chk in core.checks():
                for lv in ("L2", "L3"):
                    if lv not in levels:
                        results.append(CheckResult(
                            benchmark_id=chk.benchmark_id, subcategory_id=chk.subcategory_id,
                            requirement=chk.requirement, level=lv, verdict=Verdict.evidence_missing,
                            rationale=f"No {lv} evidence attached. Required: {chk.evidence_inputs or 'see rubric'}.",
                            confidence=1.0,
                        ))
        return sorted(results, key=lambda r: (r.benchmark_id, r.level))

    async def _subcategory(self, core: Core, sub: Subcategory, levels: list[str], shared: list[dict],
                           sources: dict[str, SourceIndex], we_ids: set[str], usage: CallUsage) -> list[CheckResult]:
        wanted = {(c.benchmark_id, lv) for c in sub.checks for lv in levels}
        got: dict[tuple[str, str], LLMCheck] = {}
        for attempt in range(2):
            pending = sorted(wanted - set(got))
            if not pending:
                break
            todo_sub = sub if attempt == 0 else sub.model_copy(
                update={"checks": [c for c in sub.checks if any(c.benchmark_id == p[0] for p in pending)]})
            req = Request(
                task=f"evaluate.{core.id}.{sub.id}" + ("" if attempt == 0 else ".retry"),
                model=self.model, system=prompts.SYSTEM, shared=shared,
                prompt=prompts.subcategory_prompt(core, todo_sub, levels),
                schema=SubcategoryAssessment, effort=self.effort,
                meta={"core": core, "subcategory": todo_sub, "levels": levels},
            )
            try:
                out: SubcategoryAssessment = await self.llm.structured(req, usage)  # type: ignore[assignment]
            except LLMError:
                if attempt == 1:
                    break
                continue
            for c in out.checks:
                key = (c.benchmark_id, c.level)
                if key in wanted and key not in got and self._citations_ok(c, sources):
                    got[key] = c
        core_ids = {c.benchmark_id for c in core.checks()}
        out_results = []
        for chk in sub.checks:
            for lv in levels:
                c = got.get((chk.benchmark_id, lv))
                if c is None:
                    out_results.append(CheckResult(
                        benchmark_id=chk.benchmark_id, subcategory_id=sub.id, requirement=chk.requirement,
                        level=lv, verdict=Verdict.evidence_missing, confidence=0.0,
                        rationale="Not reliably assessed (no verifiable model answer); review manually.",
                    ))
                    continue
                src = sources[lv]
                refs = [EvidenceRef(quote=q, source="sop" if lv == "L1" else f"evidence:{lv}",
                                    verified=src.contains(q),
                                    work_element_id=c.work_element_ids[0] if c.work_element_ids else None)
                        for q in c.quotes]
                conf = c.confidence
                if c.quotes and not any(r.verified for r in refs):
                    conf = min(conf, 0.3)
                # needs L3 only makes sense for an L1 check the model couldn't judge, and only while no L3 is attached
                needs = lv == "L1" and c.needs_l3 and c.verdict == "evidence_missing" and "L3" not in levels
                out_results.append(CheckResult(
                    benchmark_id=chk.benchmark_id, subcategory_id=sub.id, requirement=chk.requirement,
                    level=lv, verdict=Verdict(c.verdict), rationale=clean_text(c.rationale) or "", evidence=refs,
                    confidence=conf, work_element_ids=[w for w in c.work_element_ids if w in we_ids],
                    root_of=c.root_of if c.root_of in core_ids and c.root_of != chk.benchmark_id else None,
                    suggested_fix=clean_text(c.suggested_fix), needs_level="L3" if needs else None,
                ))
        return out_results

    @staticmethod
    def _citations_ok(c: LLMCheck, sources: dict[str, SourceIndex]) -> bool:
        """A 'met' must be backed by at least one quote that exists in the source; otherwise ask again."""
        if c.verdict != "met":
            return True
        return any(sources[c.level].contains(q) for q in c.quotes)
