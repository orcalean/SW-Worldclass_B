# 0005. SOP required; L2/L3 evidence optional; missing evidence is never N/A

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner (chose "SOP + optional evidence")

## Context
L1 is judged from the SOP alone. L2 needs station evidence (photos, displays); L3 needs governing documents (specs, Control Plan, PFMEA).

## Decision
- The SOP is the only required input. L2/L3 evidence files can be attached per revision (`POST /v1/sops/{id}/revisions/{n}/evidence`).
- A level with no attached evidence is resolved in code to `evidence_missing` for every check, with no LLM call (`Assessor.assess` in `app/evaluation/assessor.py`).
- `evidence_missing` is never treated as `not_applicable`.

## Consequences
- Without evidence, L2/L3 cost nothing and the gate stays at "evidence required".
- Evidence documents contribute their text layer; photos get a Haiku vision description.
