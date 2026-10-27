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

## Black-box API
```bash
curl -F file=@sop.pdf localhost:8000/v1/ingest                       # file -> job -> SOPDocument
curl -H 'content-type: application/json' \
     -d '{"sop_document": {...}, "evidence": []}' localhost:8000/v1/evaluate   # -> job -> EvaluationResult
curl localhost:8000/v1/jobs/<job_id>                                  # status + inline result
```

More: `CLAUDE.md` (index for agents and developers) and `docs/`.
