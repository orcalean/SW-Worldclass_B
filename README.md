# sw-world-class · backend

SOP benchmark audit API (SWP Step 2 · SWI · SQDCME). Upload any SOP, get a deterministic benchmark score, gates, traceable findings and an improvement guide against the OracLean rubric (L1 SWI · L2 station · L3 governing). The UI lives in a separate repo (`../frontend`).

```
file ─► [A] ingestion ─► SOPDocument ─► [B] evaluation (LLM) ─► verdicts ─► [C] scoring (pure code) ─► EvaluationResult
                              ▲ other apps (SWP, Ph2) can POST this directly
```

## Run
```bash
cp .env.example .env            # set ANTHROPIC_API_KEY, or SWC_LLM_PROVIDER=offline for a heuristic demo
uv sync
uv run uvicorn app.main:app --port 8000      # OpenAPI at http://localhost:8000/docs
uv run pytest
```
Both apps at once: from the parent folder, `docker compose up --build`.

## Users
There is no sign-up page; users are added from the CLI. Each user only sees the SOPs they uploaded.
```bash
uv run python -m app.auth.seed you@x.com --name "You"     # add a user, or reset their password (prompts)
uv run python -m app.auth.seed you@x.com --password 'pw'  # same, without the prompt
uv run python -m app.auth.seed --file users.json          # many at once: [{"email","name","password"}, ...]
uv run python -m app.auth.seed --list                     # show all users
uv run python -m app.auth.seed you@x.com --claim-orphans  # give SOPs with no owner to this user (one-time, after
                                                          # upgrading; old SOPs stay hidden until claimed)
uv run python -m app.auth.seed you@x.com --deactivate     # block login and end their sessions
```
Local dev without login: set `SWC_AUTH_REQUIRED=false` in `.env`.

## Black-box API
```bash
curl -F file=@sop.pdf localhost:8000/v1/ingest                       # file -> job -> SOPDocument
curl -H 'content-type: application/json' \
     -d '{"sop_document": {...}, "evidence": []}' localhost:8000/v1/evaluate   # -> job -> EvaluationResult
curl localhost:8000/v1/jobs/<job_id>                                  # status + inline result
```

More: `CLAUDE.md` (index for agents and developers) and `docs/`.
