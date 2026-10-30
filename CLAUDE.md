# sw-world-class · backend

SOP benchmark audit API (SWP Step 2 · SWI · SQDCME). Takes any SOP, extracts it into a canonical `SOPDocument`, evaluates it against OracLean rubrics at L1 (SWI) / L2 (station) / L3 (governing) and returns a deterministic score, gates, traceable findings and an improvement guide. A black-box API usable by any app. The UI is a **separate repo** (`../frontend`) that talks to this API over HTTP only. FastAPI, Python ≥ 3.11, `uv`.

## Working rules
1. **Ask before deciding.** If a decision isn't covered by the docs or ADRs, ask the owner (with options). Always ask before architectural, product or UX decisions.
2. **Follow the ADRs** in `docs/decisions/`. Don't reverse one without asking; add an ADR for each new decision the owner confirms.
3. **Keep docs true.** If you change behaviour a doc describes, update that doc in the same change.
4. **End every task with `/handoff`.**
5. **Go step by step.** The owner prefers small steps and short summaries.
6. Invariants:
   - Scoring (`app/scoring/`) never calls an LLM; LLM calls only go through `app/llm/client.py`.
   - Ingestion transcribes, never judges. Evaluation never parses files.
   - `SOPDocument` / `EvaluationResult` are public contracts: changes are breaking; tell the frontend repo to run `npm run gen:api`.
   - Rubrics and policy are data (`rubrics/`); don't hard-code checks or weights.
   - Bump `EXTRACT_PROMPT_VERSION` / `PROMPT_VERSION` / `ENGINE_VERSION` / rubric or policy `version` when behaviour changes (they key the caches).
   - `offline` provider results are heuristic demos and must stay labelled.
   - Schema changes only via Alembic migrations; never `create_all`.
   - Never commit `.env`. Don't commit unless the owner asks.

## Read
| When you… | Read |
|---|---|
| start anything | `docs/progress/STATUS.md`, latest `docs/progress/log/*` |
| need the big picture | `docs/architecture/overview.md` |
| change API / contracts / module boundaries | `docs/design/backend-design.md` |
| touch ingestion | `docs/features/ingestion.md` |
| touch evaluation or scoring | `docs/features/evaluation-and-scoring.md` |
| touch storage or auth | `docs/architecture/data-model.md`, `docs/architecture/auth-and-access.md` |
| want to know why | `docs/decisions/README.md` |

## Layout
```
app/
  main.py               FastAPI app, CORS, lifespan (marks interrupted jobs failed)
  config.py             Settings from env + .env (prefix SWC_; ANTHROPIC_API_KEY unprefixed)
  api/v1/routes.py      combines the v1 routers below into one `router` (main.py includes it); adds require_auth
  api/v1/auth.py        /v1/auth/login, logout, me (public)
  api/v1/health.py      /v1/health
  api/v1/rubrics.py     /v1/rubrics[/{id}]
  api/v1/jobs.py        /v1/ingest, /v1/evaluate, /v1/jobs/{id} (black-box)
  api/v1/sops.py        /v1/sops/... revisions, document review, evidence, assess (workspace)
  api/v1/assessments.py /v1/assessments/{id}, /v1/blobs/{sha}/{name}
  api/v1/common.py      shared: JobRef/JobOut, read_upload (size/type checks)
  auth/__init__.py      password hashing, DB sessions, require_auth (cookie or X-API-Key)
  auth/seed.py          CLI to add / reset / list / deactivate users
  services.py           orchestration: providers, extraction/result caches, persistence
  contracts/            public contracts: sop.py, evidence.py, evaluation.py, rubric.py
  ingestion/            A · loaders.py (file → pages), structurer.py (pages → SOPDocument), offline.py
  evaluation/           B · assessor.py, prompts.py, verifier.py, engine.py, offline.py
  scoring/              C · scorer.py (roll-up, gates), improvements.py (overlay, guide)
  rubric/               importer.py (xlsx → JSON), registry.py (catalogue + policy)
  llm/client.py         LLM protocol, AnthropicLLM, ScriptedLLM, pricing/usage
  storage/db.py         SQLAlchemy models, session(), Blobs
  storage/migrate.py    runs Alembic upgrade on first connect
  jobs/runner.py        in-process async jobs backed by the jobs table
migrations/             Alembic env.py + versions/ (schema history)
rubrics/                dimensions.json, policy@1.0.json, quality/core1@1.0.json, source/*.xlsx
tests/unit/             test_rubric, test_scorer, test_evaluation, test_ingestion, test_api, test_auth
tests/fixtures/         badge_sop.json
docs/                   architecture/, design/, features/, decisions/, progress/
```

## Commands
```bash
uv sync
uv run uvicorn app.main:app --port 8000     # reads .env; SWC_LLM_PROVIDER=offline for a no-key demo
uv run pytest                                # 36 tests; always on a temp SQLite file, never the .env database
uv run alembic revision --autogenerate -m "x" # after changing models in app/storage/db.py; review + commit the file
uv run alembic upgrade head                  # apply migrations (the app also does this on first connect)
uv run python -m app.auth.seed you@x.com --name "You"   # add / reset a login user (prompts for password)
uv run python -m app.auth.seed you@x.com --claim-orphans  # SOPs with no uploader (pre-ADR 0010 / API key) -> you
uv run python -m app.rubric.importer rubrics/source/<file>.xlsx rubrics/quality/core1@1.0.json --dimension Q --core 1 --version 1.0
# from the parent folder: docker compose up --build   → API + UI together (rebuild after dependency or migration changes)
```

## Adding an endpoint
1. Pick the module in `app/api/v1/` for that area (or add one with its own `router = APIRouter(...)` and list it in `routes.py`). Put request/response models at the top of that module (or reuse a contract from `app/contracts/`).
2. Add the handler to that module's `router`. Keep it thin: validate, call `services.*` or a module, map to the response model. Auth comes from the router dependency `require_auth` (session cookie or `X-API-Key`). Anything touching a SOP takes `user: Me` and loads it through `_get_sop` / `_get_revision` in `sops.py`, so other users get 404 (ADR 0010).
3. Anything that calls an LLM or takes seconds runs as a job: `runner.submit(kind, work)` where `work(stage)` returns `(result_type, result_id, inline_result)`; respond `202` with the job id (see the `ingest` / `evaluate` handlers).
4. DB: `with db.session() as ses: ...; ses.commit()`. New tables/columns go in `app/storage/db.py`, then `uv run alembic revision --autogenerate` (review the file; it ships with the change).
5. Test in `tests/unit/test_api.py` with the `client` fixture (offline provider, temp data dir); `await wait(client, job_id)` for jobs.
6. `uv run pytest`; if a contract changed, note it in the handoff so the frontend regenerates types.

## Conventions
- Modules A/B/C are storage-agnostic; persistence and caching live in `services.py`.
- LLM calls: build a `Request`, call `llm.structured(req, usage)`; outputs are Pydantic schemas.
- Check ids only as data (`OWNER_BY_SUBCATEGORY` in `scoring/improvements.py` is the one current exception).
- Type hints everywhere, `from __future__ import annotations`, ruff line length 110.

## Env vars (`.env`, see `.env.example`)
| Var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Claude credentials (else SDK resolution, e.g. `ant auth login`) |
| `SWC_LLM_PROVIDER` | `anthropic` | `offline` = heuristic demo/test provider |
| `SWC_EXTRACTION_MODEL` / `SWC_EVALUATION_MODEL` / `SWC_CHEAP_MODEL` | sonnet-5-5 / sonnet-5-5 / haiku-5-5 | models |
| `SWC_EXTRACTION_EFFORT` / `SWC_EVALUATION_EFFORT` | low / medium | `output_config.effort` |
| `SWC_REFUSAL_FALLBACK` | true | server-side refusal fallback |
| `SWC_MAX_CONCURRENCY`, `SWC_PAGES_PER_EXTRACTION_CALL` | 6, 4 | throughput |
| `SWC_DATA_DIR` | `./data` (relative to cwd) | SQLite file + blobs |
| `DATABASE_URL` | – | Supabase transaction pooler (:6543), used by the app |
| `DIRECT_URL` | – | Supabase session/direct (:5432), used by migrations |
| `SWC_DATABASE_URL` | – | overrides `DATABASE_URL` (tests); none set = SQLite in data dir |
| `SWC_API_KEYS` | empty | comma-separated keys for `X-API-Key` (service callers) |
| `SWC_AUTH_REQUIRED` | true | login required on `/v1`; false = open unless `SWC_API_KEYS` set (local dev) |
| `SWC_SESSION_DAYS` | 7 | login session lifetime |
| `SWC_COOKIE_SECURE` | false | set true behind HTTPS |
| `SWC_CORS_ORIGINS` | `http://localhost:5173` | comma-separated |

## Gotchas
- `get_settings()` and `db._sessionmaker()` are `lru_cache`d; tests clear them in `tests/conftest.py`.
- Tests load `.env` too; `tests/conftest.py` forces `SWC_DATABASE_URL` to temp SQLite so they never hit Supabase. Keep it that way.
- Supabase transaction pooler (:6543) can't use prepared statements: the engine sets `prepare_threshold=None`. Don't remove it.
- The API rejects `temperature`; Sonnet 5.5 rejects forced `tool_choice`. Use `beta.messages.stream(output_format=...)` + `get_final_message()` (non-streaming calls with large `max_tokens` are refused by the SDK).
- Header metadata is indexed as `field: value` for quote verification (`SOPDocument.all_text`).
- Without LibreOffice, DOCX/PPTX/XLSX fall back to native extraction (no page renders).
- Tests run with `SWC_AUTH_REQUIRED=false` (conftest); `test_auth.py` turns login on for its own client.
- Signed-in users only see SOPs they uploaded (ADR 0010); after upgrading, old SOPs are hidden until `--claim-orphans`.
- With login on, the local UI needs a seeded user (`python -m app.auth.seed`), or set `SWC_AUTH_REQUIRED=false` in `.env`.

## How to verify
- Any change: `uv run pytest` passes.
- Contract change: also confirm the frontend repo's `npm run gen:api && npx tsc --noEmit -p .`.
