# Architecture Decision Records

One file per decision confirmed with the owner. Don't reverse an accepted ADR without asking the owner; supersede it with a new ADR instead.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-separate-fastapi-backend-and-react-frontend.md) | Separate FastAPI backend and React frontend | Accepted | 2026-10-24 |
| [0002](0002-three-modules-one-sop-contract.md) | Ingestion, evaluation and scoring as separate modules joined by one SOPDocument contract | Accepted | 2026-10-24 |
| [0003](0003-claude-tiered-models-with-caching.md) | Claude Sonnet 5.5 / Haiku 5.5, tiered, with prompt caching | Accepted | 2026-10-24 |
| [0004](0004-core1-full-other-cores-as-slots.md) | Implement Quality Core 1 fully; other dimensions and cores are "Not assessed" slots | Accepted | 2026-10-24 |
| [0005](0005-sop-required-l2-l3-evidence-optional.md) | SOP required; L2/L3 evidence optional; missing evidence is never N/A | Accepted | 2026-10-24 |
| [0006](0006-l1-headline-score.md) | Headline score is L1; L2/L3 shown as evidence completeness and only hold the gate | Accepted | 2026-10-24 |
| [0007](0007-scoring-policy-defaults.md) | Scoring policy defaults (points, weights, blocking checks, N/A rule) | Accepted | 2026-10-24 |

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD
- Decided by: <owner / who confirmed>

## Context
Why a decision was needed; constraints.

## Decision
What we do.

## Consequences
What gets easier, what gets harder, follow-ups.
```
