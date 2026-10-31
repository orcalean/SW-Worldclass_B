# 2026-10-31 · Levels kept apart + golden set

**Why:** client: "the result mixes L1, L2, L3". Result was also too long (45 actions for one 6-step SOP).

**Done**
- Strict L1 prompt (`eval-1.1`): judge only the SOP; conditional rules whose trigger only L3 can establish → `evidence_missing` + `needs_level = "L3"`; L1 fixes must be SOP edits. `clean_text` strips leaked JSON.
- Contract 1.1 (additive): `CheckResult.needs_level`, `Improvement.level`, `Gate.missing_evidence`; `gate.reasons` now L1 blocking only.
- Steps, core status and dimension summary from L1 only; L1 `needs_level` checks are listed in the L3 evidence item instead of getting an L1 fix. ENGINE 0.2.0.
- Golden set `tests/golden/badge/` (client's v3, V1.1 before, V2.0 after) + `tests/golden/run.py` (own SQLite, never the app DB).
- Fixed `sqlalchemy_url` mangling relative SQLite URLs.
- Frontend: step grid shows L1 fixes only; separate "L2 / L3 · evidence to attach" card; "Needs L3" badge on checks.

**First golden run ($0.65)**
| file | L1 score | gate | L1 fixes | needs L3 |
|---|---|---|---|---|
| SOP-0002 v3 | 46.3 | evidence_required | 25 | 17 |
| SW-0002 V1.1 (before) | 63.1 | evidence_required | 20 | 19 |
| SW-0002 V2.0 (after) | 66.1 | evidence_required | 26 | 12 |
Ranking correct; V2.0 passes 7-01 / 11-03 / 3-01; 'before' fixes cover 8/11 of the client's own changes. Problems: see STATUS todo (needs_l3 over-used on red cards; weak separation; too many partials).
