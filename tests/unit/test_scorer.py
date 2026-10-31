import random

from app.contracts.evaluation import CheckResult, Verdict
from app.rubric.registry import load_catalogue
from app.scoring.scorer import score

CAT = load_catalogue()
CORE = CAT.assessed_cores()[0]


def cr(bid, level="L1", verdict=Verdict.met, rationale="ok", **kw):
    chk = CAT.check(bid)
    return CheckResult(benchmark_id=bid, subcategory_id=chk.subcategory_id, requirement=chk.requirement,
                       level=level, verdict=verdict, rationale=rationale, **kw)


def all_met(level="L1"):
    return [cr(c.benchmark_id, level) for c in CORE.checks()]


def sub(dims, sid):
    q = next(d for d in dims if d.key == "Q")
    return next(s for s in q.cores[0].subcategories if s.id == sid)


def test_worked_example_subcategory_1_3():
    rs = [r for r in all_met() if not r.benchmark_id.startswith("Q01-3-")] + [
        cr("Q01-3-01", verdict=Verdict.gap),
        cr("Q01-3-02"),
        cr("Q01-3-03"),
        cr("Q01-3-04", verdict=Verdict.partial),
        cr("Q01-3-05", verdict=Verdict.not_applicable, rationale="No count/frequency rule for a badge"),
    ]
    overall, gate, dims, _ = score(CAT, rs)
    assert sub(dims, "1.3").levels["L1"].score == 62.5
    # 11 subcategories at 100 + one at 62.5, equally weighted
    assert overall.score == round((11 * 100 + 62.5) / 12, 1)
    assert gate.status == "blocked" and gate.blocking == ["Q01-3-01"]
    assert overall.status == "not_verified"


def test_high_score_still_blocked_by_blocking_gap():
    rs = [r if r.benchmark_id != "Q01-11-01" else cr("Q01-11-01", verdict=Verdict.gap) for r in all_met()]
    overall, gate, _, _ = score(CAT, rs)
    assert overall.score >= 90
    assert gate.status == "blocked" and overall.status == "not_verified"


def test_missing_l2_l3_does_not_lower_l1_but_holds_gate():
    rs = all_met("L1") + [cr(c.benchmark_id, lv, Verdict.evidence_missing, "no station evidence")
                          for c in CORE.checks() for lv in ("L2", "L3")]
    overall, gate, _, _ = score(CAT, rs)
    assert overall.score == 100.0
    assert gate.status == "evidence_required"
    assert overall.evidence_completeness == {"L1": 100.0, "L2": 0.0, "L3": 0.0}
    assert overall.status == "not_verified"


def test_verified_when_everything_met():
    rs = all_met("L1") + all_met("L2") + all_met("L3")
    overall, gate, _, _ = score(CAT, rs)
    assert gate.status == "passed" and overall.status == "benchmark_verified"


def test_na_without_reason_becomes_evidence_missing():
    rs = [r if r.benchmark_id != "Q01-12-01" else cr("Q01-12-01", verdict=Verdict.not_applicable, rationale=" ")
          for r in all_met()]
    _, _, dims, results = score(CAT, rs)
    assert next(r for r in results if r.benchmark_id == "Q01-12-01").verdict == Verdict.evidence_missing
    assert sub(dims, "1.12").levels["L1"].evidence_missing == 1


def test_consequence_of_root_gap_not_double_counted():
    rs = [r for r in all_met() if r.benchmark_id not in ("Q01-3-01", "Q01-3-04")] + [
        cr("Q01-3-01", verdict=Verdict.gap),
        cr("Q01-3-04", verdict=Verdict.gap, root_of="Q01-3-01"),
    ]
    _, _, dims, _ = score(CAT, rs)
    # only the root counts: 3 met + 1 gap over 4 scored
    assert sub(dims, "1.3").levels["L1"].score == 75.0


def test_root_of_ignored_when_root_is_not_a_gap():
    rs = [r for r in all_met() if r.benchmark_id != "Q01-3-04"] + [
        cr("Q01-3-04", verdict=Verdict.gap, root_of="Q01-3-01")]
    _, _, dims, _ = score(CAT, rs)
    assert sub(dims, "1.3").levels["L1"].score == 80.0


def test_placeholder_dimensions_not_assessed():
    _, _, dims, _ = score(CAT, all_met())
    assert {d.key for d in dims if not d.assessed} == set("SDCME")
    q = next(d for d in dims if d.key == "Q")
    assert [c.assessed for c in q.cores] == [True, False, False, False]


def test_deterministic_regardless_of_input_order():
    rng = random.Random(7)
    verdicts = [Verdict.met, Verdict.partial, Verdict.gap, Verdict.evidence_missing]
    rs = [cr(c.benchmark_id, lv, rng.choice(verdicts)) for c in CORE.checks() for lv in ("L1", "L2", "L3")]
    base = score(CAT, rs)
    for _ in range(5):
        shuffled = rs[:]
        rng.shuffle(shuffled)
        again = score(CAT, shuffled)
        assert again[0] == base[0] and again[1] == base[1] and again[2] == base[2]


# --- levels are never mixed ---------------------------------------------------------------------------------

def _missing(level):
    return [cr(c.benchmark_id, level, Verdict.evidence_missing) for c in CORE.checks()]


def test_gate_reasons_are_l1_only_and_missing_evidence_is_separate():
    rs = [r if r.benchmark_id != "Q01-8-02" else cr("Q01-8-02", verdict=Verdict.gap) for r in all_met()]
    _, gate, _, _ = score(CAT, rs + _missing("L2") + _missing("L3"))
    assert gate.reasons == ["Q01-8-02 · " + CAT.check("Q01-8-02").requirement]
    assert gate.missing_evidence == ["L2", "L3"]


def test_step_status_ignores_l2_l3():
    from app.contracts.sop import SOPDocument
    from app.scoring.improvements import overlay

    doc = SOPDocument.model_validate({"source": {"format": "pdf", "sha256": "x", "pages": 1},
                                      "work_elements": [{"id": "we-1", "seq": 1, "title": "Load badge"}]})
    rs = [cr("Q01-1-01", work_element_ids=["we-1"]),
          cr("Q01-1-01", "L2", Verdict.evidence_missing, work_element_ids=["we-1"])]
    w = overlay(doc, rs)[0]
    assert w.status == "verified" and w.check_ids == ["Q01-1-01"]


def test_needs_l3_check_moves_to_the_l3_item_not_an_l1_fix():
    from app.scoring.improvements import improvements

    rs = [r if r.benchmark_id != "Q01-10-03" else
          cr("Q01-10-03", verdict=Verdict.evidence_missing, needs_level="L3",
             rationale="Only the Control Plan says whether operator awareness is required.")
          for r in all_met()] + _missing("L2") + _missing("L3")
    items = improvements(CAT, score(CAT, rs)[3])
    assert not [i for i in items if i.level == "L1"]
    l3 = next(i for i in items if i.level == "L3")
    assert "Q01-10-03" in l3.action and l3.priority == "evidence"
    assert {i.level for i in items} == {"L2", "L3"}
