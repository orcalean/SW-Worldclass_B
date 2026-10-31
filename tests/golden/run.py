"""Golden-set runner: real Claude calls on client SOPs, compared with what the client expects.

    uv run python -m tests.golden.run            # all sets under tests/golden/
    uv run python -m tests.golden.run badge      # one set

Costs real money (~$0.15-0.25 per SOP on first run). Never touches the app database: it uses its own SQLite file
and blob dir in tests/golden/.work/, so re-runs reuse extractions and unchanged results for free.
Exit code 1 when a hard expectation fails (strict ranking, after_must_not_fail).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent
WORK = GOLDEN / ".work"
WORK.mkdir(exist_ok=True)
# Must be set before app settings are read: keep the golden run away from the real database.
os.environ["SWC_DATA_DIR"] = str(WORK)
os.environ["SWC_DATABASE_URL"] = f"sqlite:///{WORK / 'golden.db'}"
os.environ["DIRECT_URL"] = ""

from app import services  # noqa: E402
from app.contracts.evaluation import EvaluationResult  # noqa: E402


def _checks(res: EvaluationResult, level: str = "L1") -> dict:
    return {c.benchmark_id: c for d in res.dimensions for co in d.cores for s in co.subcategories
            for c in s.checks if c.level == level}


async def _run_file(path: Path) -> tuple[EvaluationResult, float]:
    doc, extract_cost = await services.ingest_bytes(path.name, path.read_bytes())
    _, res = await services.assess(doc, [])
    return res, extract_cost + res.usage.cost_usd


async def run_set(folder: Path) -> tuple[dict, bool]:
    exp = json.loads((folder / "expected.json").read_text())
    results: dict[str, EvaluationResult] = {}
    rows, cost = [], 0.0
    for name, meta in exp["files"].items():
        res, c = await _run_file(folder / name)
        results[name] = res
        cost += c
        l1 = _checks(res)
        fixes = [i for i in res.improvements if i.level == "L1"]
        rows.append({
            "file": meta["label"], "role": meta["role"], "l1_score": res.overall.score, "gate": res.gate.status,
            "blocking": res.gate.blocking, "l1_fixes": len(fixes), "all_items": len(res.improvements),
            "needs_l3": sorted(k for k, c in l1.items() if c.needs_level),
            "verdicts": {v: sum(1 for c in l1.values() if c.verdict.value == v)
                         for v in ("met", "partial", "gap", "evidence_missing", "not_applicable")},
            "cost_usd": round(c, 4), "cached": res.usage.cached_result,
        })

    failures, notes = [], []
    score = {n: (r.overall.score or 0) for n, r in results.items()}
    for lo, hi in exp.get("strict_ranking", []):
        if not score[lo] < score[hi]:
            failures.append(f"ranking: {lo} ({score[lo]}) should score below {hi} ({score[hi]})")
    order = exp["ranking_low_to_high"]
    if [score[n] for n in order] != sorted(score[n] for n in order):
        notes.append("soft ranking not followed: " + " < ".join(f"{n}={score[n]}" for n in order))

    after = next(n for n, m in exp["files"].items() if m["role"] == "after")
    after_l1 = _checks(results[after])
    for bid, why in exp.get("after_must_not_fail", {}).items():
        v = after_l1[bid].verdict.value if bid in after_l1 else "missing"
        if v == "gap":
            failures.append(f"{after}: {bid} is a gap but should not be ({why}). Model said: {after_l1[bid].rationale}")

    # Do the 'before' fixes point at what the client actually changed? (keyword match, informative)
    before = next(n for n, m in exp["files"].items() if m["role"] == "before")
    text = " ".join(f"{i.title} {i.action}" for i in results[before].improvements if i.level == "L1").lower()
    covered = {t: any(k in text for k in kws) for t, kws in exp.get("client_changes_before_to_after", {}).items()}

    # L1 purity: L1 fixes must not demand governing-document content.
    leaks = []
    for name, res in results.items():
        for i in res.improvements:
            if i.level == "L1":
                text_i = f"{i.title} {i.action}".lower()
                hit = [t for t in exp.get("l1_must_not_demand", []) if re.search(rf"\b{re.escape(t)}\b", text_i)]
                if hit:
                    leaks.append({"file": name, "checks": i.check_ids, "terms": hit, "title": i.title})

    report = {"set": exp["name"], "rows": rows, "client_change_coverage": covered,
              "coverage": f"{sum(covered.values())}/{len(covered)}", "l1_purity_leaks": leaks,
              "failures": failures, "notes": notes, "cost_usd": round(cost, 4)}
    return report, not failures


def _print(report: dict) -> None:
    print(f"\n== {report['set']}")
    print(f"{'file':<14}{'role':<8}{'L1 score':>9}  {'gate':<18}{'L1 fixes':>9}{'needs L3':>10}  blocking")
    for r in report["rows"]:
        print(f"{r['file']:<14}{r['role']:<8}{r['l1_score']!s:>9}  {r['gate']:<18}{r['l1_fixes']:>9}"
              f"{len(r['needs_l3']):>10}  {', '.join(r['blocking']) or '-'}")
    print(f"client changes covered by 'before' L1 fixes: {report['coverage']}  "
          + ", ".join(f"{'✔' if v else '✘'} {k}" for k, v in report["client_change_coverage"].items()))
    print(f"L1 fixes demanding L3 content: {len(report['l1_purity_leaks'])}")
    for x in report["l1_purity_leaks"]:
        print(f"   - {x['file']} {x['checks']}: {x['terms']} · {x['title'][:90]}")
    for n in report["notes"]:
        print(f"note: {n}")
    for f in report["failures"]:
        print(f"FAIL: {f}")
    print(f"cost this run: ${report['cost_usd']}")


async def main(only: list[str]) -> int:
    ok_all = True
    for folder in sorted(p for p in GOLDEN.iterdir() if (p / "expected.json").exists()):
        if only and folder.name not in only:
            continue
        report, ok = await run_set(folder)
        (WORK / f"{folder.name}-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        _print(report)
        ok_all &= ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
