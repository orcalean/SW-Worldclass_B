# 2026-10-24 · Env split per app + agent docs system

## What was done
- Env files moved into each app: [backend/.env.example](../../../backend/.env.example), [frontend/.env.example](../../../frontend/.env.example) (real `.env` files beside them, git-ignored). The old root `.env` was moved to `backend/.env` unchanged.
- Bug fix: `ANTHROPIC_API_KEY` in `backend/.env` was never passed to the SDK. Now read by [backend/app/config.py](../../../backend/app/config.py) and passed in [backend/app/services.py](../../../backend/app/services.py) → [backend/app/llm/client.py](../../../backend/app/llm/client.py). `backend/.env` is found regardless of working directory.
- [frontend/vite.config.ts](../../../frontend/vite.config.ts) reads `API_PROXY_TARGET` via `loadEnv`; [docker-compose.yml](../../../docker-compose.yml) uses each app's env file.
- Agent docs: [CLAUDE.md](../../../CLAUDE.md) (+ `AGENTS.md` symlink), [docs/overview.md](../../overview.md), [docs/decisions/](../../decisions/README.md) (7 ADRs), [docs/progress/STATUS.md](../STATUS.md), [backend/CLAUDE.md](../../../backend/CLAUDE.md) + `backend/docs/{design,architecture,features}`, [frontend/CLAUDE.md](../../../frontend/CLAUDE.md) + `frontend/docs/{design,features}`, [.claude/commands/handoff.md](../../../.claude/commands/handoff.md).

## Decisions
- Owner: docs per app (`backend/docs`, `frontend/docs`), shared items (ADRs, progress, overview) at root.
- Owner: record confirmed decisions + the 3-module split as ADRs 0001–0007; SQLite/in-process jobs and the offline provider are documented as current state, not ADRs.
- Owner: list all known issues in STATUS; document auth as current state (API key only, no login).
- Agent: frontend features in one file (`screens.md`) to avoid many small files.

## Not done / next steps
- See STATUS Todo. Most urgent: first real audit with the API key; owner's sample SOPs for the golden set.
- Known issues found while documenting (not fixed, docs-only task): blob images vs API key, tests not isolating `SWC_DATABASE_URL`, `VITE_API_KEY` exposure.

## How to verify
```bash
cd backend && uv run pytest                      # 28 passed
uv run python -c "from app.config import Settings; print(bool(Settings().anthropic_api_key))"   # True if key set
cd ../frontend && npx tsc --noEmit -p .
```
