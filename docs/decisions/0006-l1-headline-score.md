# 0006. Headline score is L1; L2/L3 only hold the gate

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner ("go with recommend")

## Context
Most Core 1 checks also have L2/L3 criteria. Counting missing evidence as 0 would make every SOP fail and read as "the tool is wrong".

## Decision
- Each level is scored separately (`LevelScore` per subcategory, core and overall).
- `overall.score` is the L1 score. L2/L3 appear as `evidence_completeness` percentages.
- Missing required L2/L3 evidence never lowers L1; it sets the gate to `evidence_required`, so the status stays "Not verified".

## Consequences
- Implemented in `app/scoring/scorer.py` (`score`, `Gate`, `Overall`).
- Users can reach a high L1 score and still not be "Benchmark verified" until evidence is attached.
