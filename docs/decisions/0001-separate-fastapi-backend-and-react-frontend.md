# 0001. Separate FastAPI backend and React frontend

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner (chose "Python FastAPI + React"; on 2026-10-24 split them into two git repos; only docker-compose.yml stays in the parent folder)

## Context
The backend must be usable by other applications as a black box (notably the SWP SOP-management app in Ph2), independent of this UI. SOP parsing needs strong PDF/DOCX/PPTX/XLSX tooling.

## Decision
- Two independent git repos side by side: `backend/` (this repo) and `frontend/`. The parent folder holds only `docker-compose.yml` (owner: run both at once).
- Backend: Python 3.11+, FastAPI, Pydantic v2, `uv`. Publishes OpenAPI at `/docs`.
- Frontend: React 18 + Vite + TypeScript, its own `package.json`.
- The apps share nothing except HTTP. Each repo has its own `.env` / `.env.example`, docs, ADRs, STATUS and `/handoff` command.
- Frontend API types are generated from this backend's OpenAPI (frontend repo `npm run gen:api`, which expects this repo at `../backend`).

## Consequences
- Any client can use the API without the UI.
- A contract change here must be followed by `npm run gen:api` and a type-check in the frontend repo; note it in the handoff.
- Cross-repo decisions are recorded in the repo that owns them; the frontend's ADR index points here for backend decisions.
