# Status (backend)

Last updated: 2026-10-27

## Current state
Phase 1 is built end-to-end: upload → extraction review → optional L2/L3 evidence → assess → audit screen → re-upload as a new revision. Quality Core 1 (56 checks) is the only assessed rubric. Database is Supabase Postgres with Alembic migrations (ADR 0008). All 29 backend tests pass; frontend type-checks and builds. First real Claude run done on a synthetic 1-page PDF: extraction $0.015 / 17 s, evaluation $0.14 / 30 s (12 calls, cache reads working). Not yet run on a real customer SOP. Own git repo (the UI is a separate repo at `../frontend`), no commits.

## In progress
- Nothing.

## Todo
- Run real audits on the owner's sample PDFs (best case first: digital PDFs).
- Decide how conditional checks ("where relevant", e.g. 1.12 traceability) should be judged when the SOP doesn't mention them: real run marked them `gap` (owner decision).
- Root-cause de-dup only works within one subcategory call; one root (e.g. undefined force) produced ~10 gaps across subcategories (design decision needed).
- Golden set: owner to supply 5–10 real SOPs, 2–3 with expert verdicts; fill `tests/golden/`.
- Owner sign-off on scoring policy values (`rubrics/policy@1.0.json`, ADR 0007).
- Get SWP's SOP data model and align `SOPDocument` before Ph2 (ADR 0002).
- Import other cores' workbooks when available (ADR 0004).
- Build and test the Docker setup (`docker-compose.yml` in the parent folder, outside both repos).
- Decide: move uploaded files (blobs) to Supabase Storage; they're still on local disk / the Docker volume.
- User login / roles (none exist; Supabase Auth is an option; see `docs/architecture/auth-and-access.md`).
- Decide persistence/jobs for production (currently SQLite + in-process runner; not an ADR yet).

## Known issues
- **Security (frontend side):** the UI's `VITE_API_KEY` is visible in the browser bundle; tracked in the frontend repo STATUS.
- **Images break when API keys are on:** `<img src="/v1/blobs/...">` can't send `X-API-Key`, but `/v1/blobs` requires it (`app/api/v1/routes.py`, frontend repo `src/pages/ReviewPage.tsx`).
- **Jobs lost on restart:** the in-process runner marks running jobs failed at startup; clients must resubmit (`app/jobs/runner.py`).
- **Cost under-reported:** station-photo description calls (`services.evidence_from_bytes`) are not added to any assessment's `usage.cost_usd`.
- **`SWC_DATA_DIR` default is relative** (`./data`), so the data location depends on the working directory.
- Without LibreOffice (e.g. local macOS), DOCX/PPTX/XLSX use native text/image extraction without page renders; the vision model loses layout context.
- Offline provider judges only ~8 mechanical checks; everything else shows `evidence_missing`.
- Docker image never built.

## Done
- Supabase Postgres + Alembic migrations; app migrates on startup; tests isolated on temp SQLite (2026-10-27).
- Rubric importer + Core 1 JSON (56 checks, synced with the workbook by test).
- Contracts: `SOPDocument`, `EvidenceItem`, `EvaluationResult`, rubric/policy.
- Ingestion (PDF/DOCX/PPTX/XLSX/images), vision structuring, cross-page merge, coverage warnings.
- Evaluation: per-subcategory calls, cached prefix, quote verifier with retry.
- Deterministic scoring, gates, root de-dup, overlay, improvement guide.
- API (black-box + workspace), SQLite storage, blob store, async jobs, result/extraction caches.
- Env files split per app; `ANTHROPIC_API_KEY` now read from `.env`.
- Agent docs system; repos split (backend / frontend), shared root removed except `docker-compose.yml`.

- Fixed: extraction failed against real API (needed streaming for large `max_tokens`; schema too large for structured outputs); truncated output now raises `LLMError`; all-batches-failed now fails the job.

## Dropped
- Postgres + Redis/arq for Ph1 (replaced by SQLite + in-process jobs for now; revisit for production).
