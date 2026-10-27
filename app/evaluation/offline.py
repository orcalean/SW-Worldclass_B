"""Offline heuristic stand-in for the evaluation LLM (demo / tests without an API key).

Implements a handful of mechanical Core 1 L1 checks; everything else is returned as evidence_missing.
Results are labelled 'offline' in EngineInfo.models and must never be presented as a real audit.
"""
from __future__ import annotations

import json
import re

from app.contracts.sop import SOPDocument
from app.evaluation.assessor import LLMCheck, SubcategoryAssessment
from app.llm.client import Request

VAGUE = re.compile(r"\b(proper(ly)?|good|acceptable|correct(ly)?|as required|per spec|specified)\b", re.I)
NUMBER = re.compile(r"\d")


def _doc(req: Request) -> SOPDocument:
    raw = req.shared[0]["text"].removeprefix("<sop_document>\n").removesuffix("\n</sop_document>")
    return SOPDocument.model_validate(json.loads(raw))


def _check(bid, level, verdict, rationale, quotes=(), wes=(), conf=0.7, fix=None, root=None) -> LLMCheck:
    return LLMCheck(benchmark_id=bid, level=level, verdict=verdict, rationale=rationale, quotes=list(quotes),
                    work_element_ids=list(wes), confidence=conf, suggested_fix=fix, root_of=root)


def _l1(bid: str, doc: SOPDocument) -> LLMCheck:
    specs = [(we, sp) for we in doc.work_elements for sp in we.specs]
    steps = [(we, s) for we in doc.work_elements for s in we.steps]
    if bid == "Q01-3-01":
        bad = [(we, sp) for we, sp in specs if not (sp.value and NUMBER.search(sp.value))]
        if bad:
            we, sp = bad[0]
            return _check(bid, "L1", "gap", f"'{sp.characteristic}' has no numeric value ('{sp.value}').",
                          [s.text for s in we.steps][:1], [we.id], 0.8,
                          f"State {sp.characteristic} as a target with limits and units, or cite the controlled spec.")
        if specs:
            return _check(bid, "L1", "met", "All listed specifications carry numeric values.",
                          [specs[0][1].value or ""], [specs[0][0].id])
    if bid == "Q01-3-02":
        nounit = [(we, sp) for we, sp in specs if sp.value and NUMBER.search(sp.value) and not sp.unit]
        if nounit:
            we, sp = nounit[0]
            return _check(bid, "L1", "gap", f"'{sp.characteristic}' value {sp.value} has no unit.", [], [we.id],
                          fix=f"Add the unit to {sp.characteristic}.")
        withunit = [(we, sp) for we, sp in specs if sp.unit]
        if withunit:
            we, sp = withunit[0]
            q = next((s.text for s in we.steps if sp.unit in s.text), we.steps[0].text if we.steps else "")
            return _check(bid, "L1", "met", "Numeric values carry units.", [q], [we.id])
    if bid == "Q01-3-03":
        onesided = [(we, sp) for we, sp in specs if sp.direction in ("min", "max")]
        if onesided:
            we, sp = onesided[0]
            q = next((s.text for s in we.steps if re.search(r"\b(min|max)", s.text, re.I)), "")
            return _check(bid, "L1", "met", f"'{sp.characteristic}' states its limit direction.", [q], [we.id])
    if bid == "Q01-1-04":
        vague = [(we, s) for we, s in steps if VAGUE.search(s.text)]
        if vague:
            we, s = vague[0]
            return _check(bid, "L1", "gap", f"Wording '{VAGUE.search(s.text).group(0)}' is not objective.",
                          [s.text], [we.id], fix="Replace subjective wording with a defined criterion or reference.")
        return _check(bid, "L1", "met", "No subjective acceptance wording found.",
                      [steps[0][1].text] if steps else [])
    if bid == "Q01-8-02":
        if doc.meta.revision:
            return _check(bid, "L1", "met", f"Revision {doc.meta.revision} is identified.",
                          [f"revision: {doc.meta.revision}"], conf=0.9)
        return _check(bid, "L1", "gap", "No revision identified on the SOP.", conf=0.9,
                      fix="Add the controlled revision and effective date to the SOP header.")
    if bid == "Q01-11-01":
        for we in doc.work_elements:
            text = " ".join(s.text.lower() for s in we.steps)
            for a in doc.assets:
                if a.id in we.asset_ids and a.text_in_image:
                    words = [w for w in re.findall(r"[a-z]{4,}", a.text_in_image.lower())]
                    if words and not any(w in text for w in words):
                        return _check(bid, "L1", "gap",
                                      f"Image shows '{a.text_in_image}' but the written step does not mention it.",
                                      [we.steps[0].text] if we.steps else [], [we.id], 0.7,
                                      "Make the visual and written instruction one controlled source of truth.")
        return _check(bid, "L1", "met", "No visual/text contradiction detected.",
                      [steps[0][1].text] if steps else [], conf=0.5)
    if bid == "Q01-6-01" and len(doc.meta.products) > 1:
        return _check(bid, "L1", "partial", f"SOP covers {len(doc.meta.products)} products but steps do not "
                      "state which apply to which.", doc.meta.products[:1], conf=0.6,
                      fix="State product/variant applicability per work element.")
    return _check(bid, "L1", "evidence_missing", "Offline heuristic cannot judge this check.", conf=0.0)


def handler(req: Request) -> SubcategoryAssessment:
    doc = _doc(req)
    sub = req.meta["subcategory"]
    out = []
    for c in sub.checks:
        for lv in req.meta["levels"]:
            if lv == "L1":
                out.append(_l1(c.benchmark_id, doc))
            else:
                out.append(_check(c.benchmark_id, lv, "evidence_missing", "Offline heuristic does not read evidence.",
                                  conf=0.0))
    return SubcategoryAssessment(checks=out)
