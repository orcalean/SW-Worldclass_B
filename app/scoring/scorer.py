"""Module C: deterministic roll-up. Same verdicts in -> same EvaluationResult out. No LLM here.

Rules (policy-driven):
- points: met/partial/gap from policy.verdict_points; evidence_missing and not_applicable leave the denominator
- not_applicable without a rationale is treated as evidence_missing (no silent N/A)
- a check whose root_of points at another gap at the same level is a consequence: shown, not deducted
- headline score = L1; L2/L3 surface as separate scores + evidence completeness
- gate blocks on any gap in policy.blocking_checks; missing required L2/L3 evidence holds 'not verified'
"""
from __future__ import annotations

from collections import defaultdict

from app.contracts.evaluation import (
    CheckResult, CoreResult, DimensionResult, Gate, LevelScore, Overall, SubcategoryResult, Verdict,
)
from app.contracts.rubric import LEVELS, Core, ScoringPolicy
from app.rubric.registry import Catalogue

SCORED = {Verdict.met, Verdict.partial, Verdict.gap}


def normalize(results: list[CheckResult], policy: ScoringPolicy) -> list[CheckResult]:
    """Apply policy rules that change verdicts before scoring (pure; returns copies)."""
    gaps = {(r.benchmark_id, r.level) for r in results if r.verdict == Verdict.gap}
    out = []
    for r in results:
        r = r.model_copy(deep=True)
        if r.verdict == Verdict.not_applicable and policy.na_requires_reason and not r.rationale.strip():
            r.verdict = Verdict.evidence_missing
            r.rationale = "Marked N/A without justification; treated as evidence missing."
        if r.root_of and (r.root_of, r.level) not in gaps:
            r.root_of = None  # root must itself be a gap to absorb the deduction
        r.blocking = r.verdict == Verdict.gap and r.benchmark_id in policy.blocking_checks
        out.append(r)
    return out


def _level_score(checks: list[CheckResult], level: str, policy: ScoringPolicy) -> LevelScore:
    lv = [c for c in checks if c.level == level]
    num = den = 0.0
    scored = missing = na = 0
    for c in lv:
        if c.verdict == Verdict.not_applicable:
            na += 1
            continue
        if c.verdict == Verdict.evidence_missing:
            missing += 1
            continue
        if c.root_of:  # consequence of an already-counted root gap
            continue
        w = policy.check_weights.get(c.benchmark_id, 1.0)
        num += w * policy.verdict_points[c.verdict.value]
        den += w
        scored += 1
    applicable = len(lv) - na
    return LevelScore(
        level=level,
        score=round(100 * num / den, 1) if den else None,
        scored=scored, evidence_missing=missing, not_applicable=na, total=len(lv),
        evidence_completeness=round(100 * (applicable - missing) / applicable, 1) if applicable else None,
    )


def _weighted(items: list[tuple[float | None, float]]) -> float | None:
    vals = [(s, w) for s, w in items if s is not None]
    den = sum(w for _, w in vals)
    return round(sum(s * w for s, w in vals) / den, 1) if den else None


def _merge_levels(parts: list[tuple[dict[str, LevelScore], float]], policy: ScoringPolicy) -> dict[str, LevelScore]:
    out = {}
    for lv in LEVELS:
        ls = [p[lv] for p, _ in parts]
        tot = sum(x.total for x in ls)
        na = sum(x.not_applicable for x in ls)
        miss = sum(x.evidence_missing for x in ls)
        applicable = tot - na
        out[lv] = LevelScore(
            level=lv,
            score=_weighted([(p[lv].score, w) for p, w in parts]),
            scored=sum(x.scored for x in ls), evidence_missing=miss, not_applicable=na, total=tot,
            evidence_completeness=round(100 * (applicable - miss) / applicable, 1) if applicable else None,
        )
    return out


def score_core(core: Core, results: list[CheckResult], policy: ScoringPolicy) -> CoreResult:
    by_check = defaultdict(list)
    for r in results:
        by_check[r.benchmark_id].append(r)
    subs = []
    for s in core.subcategories:
        checks = [r for c in s.checks for r in sorted(by_check.get(c.benchmark_id, []), key=lambda x: x.level)]
        levels = {lv: _level_score(checks, lv, policy) for lv in LEVELS}
        subs.append(SubcategoryResult(id=s.id, name=s.name, levels=levels, checks=checks))
    levels = _merge_levels([(s.levels, policy.subcategory_weights.get(s.id, 1.0)) for s in subs], policy)
    flat = [c for s in subs for c in s.checks]
    if any(c.verdict == Verdict.gap for c in flat):
        status = "gap"
    elif any(c.verdict in (Verdict.evidence_missing, Verdict.partial) for c in flat):
        status = "evidence"
    else:
        status = "verified"
    return CoreResult(id=core.id, number=core.number, name=core.name, assessed=True,
                      status=status, levels=levels, subcategories=subs)


def score(catalogue: Catalogue, raw: list[CheckResult]) -> tuple[Overall, Gate, list[DimensionResult], list[CheckResult]]:
    policy = catalogue.policy
    results = normalize(raw, policy)
    dims: list[DimensionResult] = []
    all_cores: list[tuple[CoreResult, float]] = []
    for d in catalogue.dimensions:
        cores: list[CoreResult] = []
        for slot in d.cores:
            if slot.core is None:
                cores.append(CoreResult(id=f"{d.key}.core{slot.number}", number=slot.number, name=slot.name,
                                        assessed=False, status="not_assessed"))
                continue
            cr = score_core(slot.core, [r for r in results if r.benchmark_id in
                                        {c.benchmark_id for c in slot.core.checks()}], policy)
            cores.append(cr)
            all_cores.append((cr, policy.core_weights.get(cr.id, 1.0)))
        assessed = [c for c in cores if c.assessed]
        if not assessed:
            dims.append(DimensionResult(key=d.key, name=d.name, assessed=False, status="not_assessed",
                                        summary="Not assessed · rubric pending", cores=cores))
            continue
        l1 = _weighted([(c.levels["L1"].score, policy.core_weights.get(c.id, 1.0)) for c in assessed])
        flat = [chk for c in assessed for s in c.subcategories for chk in s.checks]
        n_block = len({c.benchmark_id for c in flat if c.blocking})
        n_gap = len({c.benchmark_id for c in flat if c.verdict == Verdict.gap and not c.root_of})
        n_ev = len({c.benchmark_id for c in flat if c.verdict == Verdict.evidence_missing})
        if n_block:
            status, summary = "bad", f"{n_block} blocking gap{'s' if n_block > 1 else ''}"
        elif n_gap:
            status, summary = "warn", f"{n_gap} gap{'s' if n_gap > 1 else ''}"
        elif n_ev:
            status, summary = "warn", f"{n_ev} evidence gap{'s' if n_ev > 1 else ''}"
        else:
            status, summary = "good", "verified"
        if l1 is not None and l1 < policy.benchmark and status == "good":
            status = "warn"
        dims.append(DimensionResult(key=d.key, name=d.name, assessed=True, score=l1, status=status,
                                    summary=summary, cores=cores))

    levels = _merge_levels([(c.levels, w) for c, w in all_cores], policy) if all_cores else {}
    headline = levels["L1"].score if levels else None
    completeness = {lv: levels[lv].evidence_completeness for lv in LEVELS} if levels else {}

    blocking = sorted({r.benchmark_id for r in results if r.blocking})
    reasons = []
    for bid in blocking:
        chk = catalogue.check(bid)
        reasons.append(f"{bid} · {chk.requirement if chk else bid}")
    missing_lv = [lv for lv in policy.require_evidence_levels if levels and (levels[lv].evidence_missing or 0) > 0]
    gate_status = "blocked" if blocking else ("evidence_required" if missing_lv else "passed")
    gate = Gate(status=gate_status, blocking=blocking, reasons=reasons +
                [f"{lv} evidence incomplete ({completeness.get(lv)}%)" for lv in missing_lv])

    verified = headline is not None and headline >= policy.benchmark and gate_status == "passed"
    if verified:
        reason = "Score at or above benchmark · all gates passed"
    elif blocking:
        reason = f"Protection gate failed · {len(blocking)} blocking gap{'s' if len(blocking) > 1 else ''}"
    elif headline is not None and headline < policy.benchmark:
        reason = f"L1 score below benchmark {policy.benchmark:g}"
    elif missing_lv:
        reason = f"Evidence gate · {' + '.join(missing_lv)} evidence required"
    else:
        reason = "Nothing scoreable"
    overall = Overall(score=headline, benchmark=policy.benchmark,
                      status="benchmark_verified" if verified else "not_verified",
                      reason=reason, evidence_completeness=completeness)
    return overall, gate, dims, results
