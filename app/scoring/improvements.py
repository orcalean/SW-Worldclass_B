"""Work-element overlay + improvement guide, derived deterministically from normalized check results."""
from __future__ import annotations

from collections import defaultdict

from app.contracts.evaluation import CheckResult, Improvement, Verdict, WorkElementOverlay
from app.contracts.sop import SOPDocument
from app.rubric.registry import Catalogue

# Default owner by Core 1 subcategory; overridable later via rubric data.
OWNER_BY_SUBCATEGORY = {
    "1.1": "SWI owner", "1.2": "Quality", "1.3": "Engineering", "1.4": "Quality",
    "1.5": "SWI owner", "1.6": "Engineering", "1.7": "Quality / Engineering", "1.8": "Document control",
    "1.9": "Quality / Production", "1.10": "Quality", "1.11": "SWI owner", "1.12": "Quality",
}
PRIORITY_ORDER = {"must_fix": 0, "benchmark": 1, "evidence": 2}


def _dim_of(benchmark_id: str) -> str:
    return benchmark_id[0]


def overlay(doc: SOPDocument, results: list[CheckResult]) -> list[WorkElementOverlay]:
    by_we: dict[str, list[CheckResult]] = defaultdict(list)
    for r in results:
        for we in r.work_element_ids:
            by_we[we].append(r)
    out = []
    for we in sorted(doc.work_elements, key=lambda w: w.seq):
        rs = by_we.get(we.id, [])
        l1 = [r for r in rs if r.level == "L1"]
        if not rs:
            status = "no_findings"  # nothing was linked to this element; never imply it passed
        elif any(r.blocking for r in rs):
            status = "blocked"
        elif any(r.verdict == Verdict.gap for r in l1):
            status = "gap"
        elif any(r.verdict in (Verdict.partial, Verdict.evidence_missing) for r in rs):
            status = "evidence"
        else:
            status = "verified"
        issues = []
        for r in sorted(rs, key=lambda r: (not r.blocking, r.verdict != Verdict.gap, r.benchmark_id)):
            if r.verdict in (Verdict.gap, Verdict.partial) and not r.root_of:
                label = r.requirement if len(r.requirement) <= 34 else r.requirement[:32] + "…"
                if label not in issues:
                    issues.append(label)
        out.append(WorkElementOverlay(
            work_element_id=we.id, seq=we.seq, title=we.title,
            dimensions=sorted({_dim_of(r.benchmark_id) for r in rs}) or [],
            status=status, issues=issues[:3],
            check_ids=sorted({r.benchmark_id for r in rs}),
        ))
    return out


def improvements(catalogue: Catalogue, results: list[CheckResult]) -> list[Improvement]:
    items: list[Improvement] = []
    seen: set[str] = set()
    for r in sorted(results, key=lambda r: (not r.blocking, r.level, r.benchmark_id)):
        if r.root_of or r.benchmark_id in seen:
            continue
        if r.verdict == Verdict.gap or (r.verdict == Verdict.partial and r.level == "L1"):
            seen.add(r.benchmark_id)
            items.append(Improvement(
                priority="must_fix" if r.blocking else "benchmark",
                title=r.suggested_fix or f"Close gap · {r.requirement}",
                action=r.rationale,
                owner_role=OWNER_BY_SUBCATEGORY.get(r.subcategory_id, "SWI owner"),
                check_ids=[r.benchmark_id] + sorted({x.benchmark_id for x in results if x.root_of == r.benchmark_id}),
                work_element_ids=r.work_element_ids, blocks_release=r.blocking,
            ))
    # Evidence needs: one item per level when none of that level was assessable (nothing uploaded),
    # otherwise one per subcategory so the owner sees exactly what is still missing.
    kind = {"L2": "station evidence (photos / video / displays)", "L3": "governing evidence (spec / Control Plan / PFMEA)"}
    missing: dict[tuple[str, str], list[CheckResult]] = defaultdict(list)
    for lv in ("L2", "L3"):
        lv_rs = [r for r in results if r.level == lv]
        lv_missing = [r for r in lv_rs if r.verdict == Verdict.evidence_missing]
        if lv_rs and len(lv_missing) == len(lv_rs):
            items.append(Improvement(
                priority="evidence", title=f"Attach {lv} {kind[lv].split(' (')[0]}",
                action=f"No {lv} evidence attached. Provide {kind[lv]}; {len(lv_rs)} checks need it for verification.",
                owner_role="Quality" if lv == "L3" else "Production",
                check_ids=sorted({r.benchmark_id for r in lv_rs}),
            ))
            continue
        for r in lv_missing:
            missing[(r.subcategory_id, lv)].append(r)
    names = {s.id: s.name for c in catalogue.assessed_cores() for s in c.subcategories}
    for (sid, lv), rs in sorted(missing.items(), key=lambda kv: (kv[0][1], [int(x) for x in kv[0][0].split(".")])):
        items.append(Improvement(
            priority="evidence",
            title=f"Attach {lv} {kind[lv].split(' (')[0]} · {sid} {names.get(sid, '')}".strip(),
            action=f"Provide {kind[lv]} so {len(rs)} check(s) can be verified.",
            owner_role="Quality" if lv == "L3" else "Production",
            check_ids=sorted(r.benchmark_id for r in rs),
        ))
    return sorted(items, key=lambda i: PRIORITY_ORDER[i.priority])
