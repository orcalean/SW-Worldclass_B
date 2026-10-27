import json
from pathlib import Path

from app.contracts.evaluation import Verdict
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.evaluation import offline
from app.evaluation.assessor import LLMCheck, SubcategoryAssessment
from app.evaluation.engine import evaluate
from app.evaluation.verifier import SourceIndex
from app.llm.client import ScriptedLLM
from app.rubric.registry import load_catalogue

CAT = load_catalogue()
DOC = SOPDocument.model_validate(json.loads((Path(__file__).parents[1] / "fixtures/badge_sop.json").read_text()))


def all_met_handler(req):
    return SubcategoryAssessment(checks=[
        LLMCheck(benchmark_id=c.benchmark_id, level=lv, verdict="met", rationale="ok",
                 quotes=["Apply badge with specified force"], confidence=0.9)
        for c in req.meta["subcategory"].checks for lv in req.meta["levels"]])


def test_verifier_fuzzy_and_rejects_invented():
    idx = SourceIndex(DOC.all_text())
    assert idx.contains("apply badge with  specified force")
    assert idx.contains("“Apply badge with specified force, minimum hold 5 s.”")
    assert not idx.contains("Apply 40 N force with torque wrench")


async def test_engine_offline_on_badge_sop():
    res = await evaluate(DOC, [], CAT, ScriptedLLM(offline.handler, "offline"), "offline")
    q = next(d for d in res.dimensions if d.key == "Q")
    flat = {(c.benchmark_id, c.level): c for core in q.cores for s in core.subcategories for c in s.checks}
    assert flat[("Q01-3-01", "L1")].verdict == Verdict.gap and flat[("Q01-3-01", "L1")].blocking
    assert flat[("Q01-11-01", "L1")].verdict == Verdict.gap  # "WIPE CLEAN" image vs text
    assert flat[("Q01-3-01", "L2")].verdict == Verdict.evidence_missing
    assert res.gate.status == "blocked" and "Q01-3-01" in res.gate.blocking
    we4 = next(w for w in res.work_elements if w.work_element_id == "we-4")
    assert we4.status == "blocked"
    assert res.improvements[0].priority == "must_fix"
    assert res.usage.llm_calls == 12  # one per subcategory, L2/L3 resolved without the LLM


async def test_invented_quote_on_met_is_retried_then_marked_unassessed():
    calls = []

    def lying(req):
        calls.append(req.task)
        return SubcategoryAssessment(checks=[
            LLMCheck(benchmark_id=c.benchmark_id, level="L1", verdict="met", rationale="ok",
                     quotes=["Torque to 12 Nm using calibrated wrench"], confidence=0.95)
            for c in req.meta["subcategory"].checks])

    res = await evaluate(DOC, [], CAT, ScriptedLLM(lying), "x")
    assert any(t.endswith(".retry") for t in calls)
    q = next(d for d in res.dimensions if d.key == "Q")
    l1 = [c for core in q.cores for s in core.subcategories for c in s.checks if c.level == "L1"]
    assert all(c.verdict == Verdict.evidence_missing and c.confidence == 0.0 for c in l1)


async def test_evidence_levels_only_called_when_evidence_attached():
    seen_levels = []

    def h(req):
        seen_levels.append(tuple(req.meta["levels"]))
        return all_met_handler(req)

    ev = [EvidenceItem(id="ev1", level="L2", kind="photo", description="Badge fixture at station 1955L")]
    await evaluate(DOC, ev, CAT, ScriptedLLM(h), "x")
    assert set(seen_levels) == {("L1", "L2")}


async def test_same_input_same_output():
    llm = ScriptedLLM(offline.handler, "offline")
    a = await evaluate(DOC, [], CAT, llm, "offline")
    b = await evaluate(DOC, [], CAT, llm, "offline")
    assert a.model_dump(exclude={"usage"}) == b.model_dump(exclude={"usage"})


async def test_evidence_improvements_collapse_when_level_has_no_evidence():
    res = await evaluate(DOC, [], CAT, ScriptedLLM(offline.handler, "offline"), "offline")
    ev = [i for i in res.improvements if i.priority == "evidence"]
    assert [i.title for i in ev] == ["Attach L2 station evidence", "Attach L3 governing evidence"]
    assert all(len(i.check_ids) == 56 for i in ev)
