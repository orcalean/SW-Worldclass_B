# 0007. Scoring policy defaults

- Status: Accepted (defaults; owner may tune values)
- Date: 2026-10-24
- Decided by: owner approved the plan after the worked example (subcategory 1.3 → 62.5%)

## Context
The rubric workbook defines what to check, not how results become a number.

## Decision
Policy lives in `rubrics/policy@1.0.json` and is applied by `app/scoring/scorer.py`:
- Points: `met` = 1, `partial` = 0.5, `gap` = 0. `not_applicable` and `evidence_missing` leave the denominator.
- `not_applicable` requires a written rationale, otherwise it becomes `evidence_missing`.
- Weights: all checks equal within a subcategory, all subcategories equal within a core (overridable per id).
- Blocking checks (a `gap` blocks "Benchmark verified" regardless of score): Q01-3-01, Q01-7-01, Q01-7-04, Q01-8-02, Q01-11-01, Q01-11-03.
- Benchmark 90. "Benchmark verified" = L1 ≥ 90 and gate `passed`.
- One root condition, one deduction: a gap with `root_of` pointing at another gap at the same level is shown but not deducted.

## Consequences
- Changing values = edit the JSON and bump its `version` (part of the result cache key).
- Values are defaults until validated on the golden set.
