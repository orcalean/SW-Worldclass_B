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
  api/v1/routes.py      every endpoint + request/response models
  services.py           orchestration: providers, extraction/result caches, persistence
  contracts/            public contracts: sop.py, evidence.py, evaluation.py, rubric.py
  ingestion/            A · loaders.py (file → pages), structurer.py (pages → SOPDocument), offline.py
  evaluation/           B · assessor.py, prompts.py, verifier.py, engine.py, offline.py
  scoring/              C · scorer.py (roll-up, gates), improvements.py (overlay, guide)
  rubric/               importer.py (xlsx → JSON), registry.py (catalogue + policy)
  llm/client.py         LLM protocol, AnthropicLLM, ScriptedLLM, pricing/usage
  storage/db.py         SQLAlchemy models, session(), Blobs
  jobs/runner.py        in-process async jobs backed by the jobs table
rubrics/                dimensions.json, policy@1.0.json, quality/core1@1.0.json, source/*.xlsx
tests/unit/             test_rubric, test_scorer, test_evaluation, test_ingestion, test_api
tests/fixtures/         badge_sop.json
docs/                   architecture/, design/, features/, decisions/, progress/
```

## Commands
```bash
uv sync
uv run uvicorn app.main:app --port 8000     # reads .env; SWC_LLM_PROVIDER=offline for a no-key demo
uv run pytest                                # 28 tests at time of writing
uv run python -m app.rubric.importer rubrics/source/<file>.xlsx rubrics/quality/core1@1.0.json --dimension Q --core 1 --version 1.0
# from the parent folder: docker compose up --build   → API + UI together (untested so far)
```

## Adding an endpoint
1. Add request/response models near the top of `app/api/v1/routes.py` (or reuse a contract from `app/contracts/`).
2. Add the handler to `router`. Keep it thin: validate, call `services.*` or a module, map to the response model. Auth comes from the router dependency `require_key`.
3. Anything that calls an LLM or takes seconds runs as a job: `runner.submit(kind, work)` where `work(stage)` returns `(result_type, result_id, inline_result)`; respond `202` with the job id (see the `ingest` / `evaluate` handlers).
4. DB: `with db.session() as ses: ...; ses.commit()`. New tables go in `app/storage/db.py` (created by `create_all`; no migrations yet).
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
| `SWC_DATABASE_URL` | SQLite in data dir | any SQLAlchemy URL |
| `SWC_API_KEYS` | empty (auth off) | comma-separated keys for `X-API-Key` |
| `SWC_CORS_ORIGINS` | `http://localhost:5173` | comma-separated |

## Gotchas
- `get_settings()` and `db._sessionmaker()` are `lru_cache`d; tests clear them in `tests/conftest.py`.
- Tests load `.env` too; the fixture doesn't override `SWC_DATABASE_URL` (STATUS known issue).
- The API rejects `temperature`; Sonnet 5.5 rejects forced `tool_choice`. Use `beta.messages.stream(output_format=...)` + `get_final_message()` (non-streaming calls with large `max_tokens` are refused by the SDK).
- Header metadata is indexed as `field: value` for quote verification (`SOPDocument.all_text`).
- Without LibreOffice, DOCX/PPTX/XLSX fall back to native extraction (no page renders).
- `/v1/blobs` is behind the API key, which breaks `<img>` tags in the UI when keys are enabled.

## How to verify
- Any change: `uv run pytest` passes.
- Contract change: also confirm the frontend repo's `npm run gen:api && npx tsc --noEmit -p .`.
