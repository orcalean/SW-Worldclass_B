# 0004. Quality Core 1 fully implemented; other cores are slots

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner (chose "Core 1 fully, rest as slots")

## Context
Only one rubric workbook exists: `rubrics/source/OracLean_Quality_Core1_Requirement_Known_Full_v1.xlsx` (12 subcategories, 56 atomic checks, L1/L2/L3 criteria). The UI shows all six SQDCME dimensions and several cores.

## Decision
- Rubrics are data. The xlsx is imported to `rubrics/quality/core1@1.0.json` by `app/rubric/importer.py`.
- `rubrics/dimensions.json` lists every dimension and core; a core with a `file` is assessed, one without is a "Not assessed" slot.
- No AI-drafted rubrics for S/D/C/M/E or other Quality cores.

## Consequences
- Adding a core = import its workbook + add the `file` to `dimensions.json`; no code change.
- The overall score currently reflects Quality Core 1 only.
- `tests/unit/test_rubric.py` fails if the committed JSON drifts from the workbook.
