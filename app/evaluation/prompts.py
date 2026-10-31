"""Versioned evaluation prompts. Bump PROMPT_VERSION on any wording change: it is part of the result cache key."""
from __future__ import annotations

import json

from app.contracts.evidence import EvidenceItem
from app.contracts.rubric import Core, Subcategory
from app.contracts.sop import SOPDocument

PROMPT_VERSION = "eval-1.1"

SYSTEM = """You are an OracLean standard-work auditor. You judge whether a Standard Work Instruction (SWI/SOP)
meets atomic benchmark checks. You do not rewrite the SOP and you do not invent facts.

Levels (never mix them):
- L1 SWI robustness: judged ONLY from the SOP document itself (its text, tables and pictures).
- L2 station readiness: judged ONLY from the attached L2 station evidence.
- L3 customer specific: judged ONLY from the attached L3 governing evidence (specs, Control Plan, PFMEA, drawings).

Strict L1:
- Judge whether the SOP, as written, is clear and complete for the operator. Do not fail the SOP for lacking content
  that only governing documents can supply: drawing or spec numbers, Control Plan / PFMEA entries, customer
  classification systems, change notices, VIN / model-year / option breakpoints, customer traceability fields.
- Many L1 criteria are conditional ("if", "when", "where relevant", "requirements from engineering documentation").
  If the SOP itself shows the condition applies (it names a variant, a critical characteristic, a Control Plan,
  a traceability step...), judge it normally. If only governing documents could tell whether it applies and no L3
  evidence is attached, return evidence_missing with needs_l3 = true and name in the rationale which document would
  decide it. Never assume the condition applies.
- needs_l3 is only for L1 checks; leave it false otherwise.

Verdicts (choose exactly one per check and level):
- met: the criterion is satisfied, and you can quote the text that satisfies it.
- partial: partly satisfied; say precisely what is missing.
- gap: the criterion applies and is not satisfied (including when required information is absent).
- evidence_missing: the material available for this level is insufficient to judge either way.
- not_applicable: the criterion cannot apply to this operation; you MUST state why in the rationale.
  If you are unsure whether it applies, use evidence_missing, never not_applicable.

Rules:
1. quotes must be copied VERBATIM from the SOP or evidence (short spans, no paraphrase). For a gap caused by
   missing information, quote the instruction where the information should have been, if one exists.
   To quote a header field from "meta", write it as "<field>: <value>", e.g. "revision: 7".
2. work_element_ids: the SOP work elements the finding concerns (use the ids given, e.g. "we-4").
3. One root condition gets one deduction. If this check fails only BECAUSE another listed check in this core
   fails for the same root condition, set root_of to that other benchmark_id. Otherwise leave it null.
4. suggested_fix: one concrete, imperative sentence a SWI owner could act on (e.g. "State application force
   as 40 ± 5 N"). Do not invent the actual value; name what must be added. For L1 it must be doable by editing
   the SOP; ask for a reference to a governing document only when the SOP already relies on one. Plain text only.
5. rationale: 1-3 sentences, specific to this SOP. No generic advice.
6. confidence: 0-1, how sure you are of the verdict given the material.
7. Judge only what the check asks. Respect the core boundary stated below.
"""


def core_context(core: Core) -> str:
    roles = "\n".join(f"- {k}: {v}" for k, v in core.level_roles.items())
    return f"Core: {core.id} {core.name}\n{core.question or ''}\n{core.boundary or ''}\nLevel roles:\n{roles}"


def sop_block(doc: SOPDocument) -> dict:
    payload = doc.model_dump(by_alias=True, exclude={"source": {"sha256"}}, exclude_none=True)
    return {"type": "text", "text": "<sop_document>\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n</sop_document>"}


def evidence_block(items: list[EvidenceItem]) -> dict | None:
    if not items:
        return None
    rows = [e.model_dump(exclude_none=True, exclude={"sha256"}) for e in sorted(items, key=lambda e: e.id)]
    return {"type": "text", "text": "<evidence>\n" + json.dumps(rows, ensure_ascii=False, sort_keys=True)
            + "\n</evidence>"}


def subcategory_prompt(core: Core, sub: Subcategory, levels: list[str]) -> list[dict]:
    lines = [core_context(core), "", f"Subcategory {sub.id} {sub.name}: {sub.purpose or ''}", "",
             f"Assess every check below at levels: {', '.join(levels)}. Return one entry per check per level.", ""]
    for c in sub.checks:
        lines.append(f"[{c.benchmark_id}] {c.requirement}")
        for lv in levels:
            lines.append(f"  {lv}: {c.criteria[lv]}")
        if c.notes:
            lines.append(f"  Boundary note: {c.notes}")
    return [{"type": "text", "text": "\n".join(lines)}]
