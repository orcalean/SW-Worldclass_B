# 0002. Three modules joined by one SOPDocument contract

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner asked that "understanding the SOP" and "evaluation/scoring" be separate modules; module boundaries proposed in the approved plan

## Context
Customer SOPs come in every shape. When integrated with SWP (Ph2), the PDF itself is not stored: SWP holds text + images and builds the PDF at runtime. Evaluation must therefore not depend on files.

## Decision
- **A · Ingestion** (`app/ingestion/`): file → `SOPDocument`. Transcribes only; never judges quality.
- **B · Evaluation** (`app/evaluation/`): `SOPDocument` + evidence + rubric → per-check verdicts. The only place (with A) that calls an LLM.
- **C · Scoring** (`app/scoring/`): verdicts → scores, gates, overlay, improvements. Pure deterministic code, no LLM.
- The contract between A and B is `SOPDocument` (`app/contracts/sop.py`); the output contract is `EvaluationResult` (`app/contracts/evaluation.py`).
- `POST /v1/evaluate` accepts a `SOPDocument` directly, so SWP can skip ingestion.

## Consequences
- Same verdicts always produce the same score; scoring is unit-testable without an LLM.
- `SOPDocument` is a public contract: changing it is a breaking API change (bump `SCHEMA_VERSION`, regenerate frontend types).
- `SOPDocument` should be aligned with SWP's SOP data model before Ph2 (open todo).
