# 2026-10-24 · Split into two repos; docs moved out of the shared root

## What was done
- Owner made `backend/` and `frontend/` separate git repos. Everything that was at the parent folder moved into the repos:
  - `CLAUDE.md` rules/index merged into [CLAUDE.md](../../../CLAUDE.md) (+ `AGENTS.md` symlink).
  - ADRs → [docs/decisions/](../../decisions/README.md); [0001](../../decisions/0001-separate-fastapi-backend-and-react-frontend.md) updated for the repo split.
  - System overview → [docs/architecture/overview.md](../../architecture/overview.md).
  - STATUS → [docs/progress/STATUS.md](../STATUS.md) (backend items only; UI items moved to the frontend repo's STATUS).
  - `/handoff` → [.claude/commands/handoff.md](../../../.claude/commands/handoff.md).
  - Rubric workbook → `rubrics/source/OracLean_Quality_Core1_Requirement_Known_Full_v1.xlsx`; [tests/unit/test_rubric.py](../../../tests/unit/test_rubric.py) path updated.
  - Root README → [README.md](../../../README.md).
- Paths in all docs rewritten to be relative to this repo; frontend files are referred to as "frontend repo `src/...`".
- `docker-compose.yml` stays in the parent folder (runs API + UI together).

## Decisions
- Owner: no shared files at the parent folder, except `docker-compose.yml` so both can run at once.
- Agent: all 7 ADRs live in the backend repo (the decisions are about backend behaviour); the frontend repo keeps a copy of 0001 and an index linking the rest.

## Not done / next steps
- Same as STATUS Todo (first real audit, golden set, policy sign-off, SWP data model, Docker test).

## How to verify
```bash
uv run pytest        # 28 passed
```
