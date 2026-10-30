# Backend design

## Principles
- **Black box.** Other apps talk only to `/v1` with the public contracts; nothing about files, storage or prompts leaks into them (ADR 0001, 0002).
- **AI reads, code decides.** The LLM transcribes (A) and gives categorical verdicts with quotes (B). Everything numeric (applicability, points, weights, gates, status, improvement ordering) is deterministic code (C).
- **Trust over coverage.** Unverifiable answers become `evidence_missing`, not guesses. Missing evidence is never N/A.
- **Repeatable.** Identical inputs return the cached result; versions of rubric, policy, prompts and engine are recorded in every result (`EvaluationResult.engine`).

## Public contracts (`app/contracts/`)
| Contract | File | Used by |
|---|---|---|
| `SOPDocument` (`schema_version` `sop-document/1.0`) | `sop.py` | output of `/v1/ingest`; input of `/v1/evaluate`; stored per revision |
| `EvidenceItem` | `evidence.py` | L2/L3 evidence (text and/or description) |
| `EvaluationResult` (`evaluation-result/1.0`) | `evaluation.py` | output of `/v1/evaluate`, `/v1/assessments/{id}` |
| `Core`, `Check`, `ScoringPolicy` | `rubric.py` | rubric JSON + policy JSON |

`SOPDocument` shape: `source`, `meta` (title, swi_id, revision, effective_date, owner, plant, line, station, products), `work_elements[]` (id, seq, title, steps[kind], specs[value/unit/tolerance/direction], quality_marks, references, asset_ids, provenance), `assets[]` (images with description and text_in_image), `global` (ppe, tools, materials, references, revision history, notes), `extraction_warnings[]`. Every element carries `provenance {page, bbox, confidence}`.

`EvaluationResult` shape: `engine` (versions, models), `overall` (L1 score, benchmark, status, reason, evidence completeness per level), `gate` (passed | blocked | evidence_required, blocking ids, reasons), `dimensions[]` → `cores[]` → `subcategories[]` → `checks[]` (verdict, rationale, quotes with `verified`, confidence, work element ids, root_of, blocking, suggested_fix), `work_elements[]` overlay, `improvements[]`, `usage` (calls, tokens, cost, cached).

## API surface (`app/api/v1/`: one router module per area, combined in `routes.py`)
| Method | Path | Kind |
|---|---|---|
| GET | `/v1/health`, `/v1/rubrics`, `/v1/rubrics/{core_id}` | black-box |
| POST | `/v1/ingest` (multipart file) → job | black-box |
| POST | `/v1/evaluate` (`{sop_document, evidence[]}`) → job | black-box |
| GET | `/v1/jobs/{id}` (status, stage, inline result) | black-box |
| GET/POST | `/v1/sops`, `GET /v1/sops/{id}` (upload; `sop_id` form field = re-upload as next revision) | workspace |
| GET/PUT | `/v1/sops/{id}/revisions/{n}/document` (PUT = human-reviewed, status `reviewed`) | workspace |
| POST/DELETE | `/v1/sops/{id}/revisions/{n}/evidence[/{evidence_id}]` | workspace |
| POST | `/v1/sops/{id}/revisions/{n}/assess` → job | workspace |
| GET | `/v1/assessments/{id}`, `/v1/blobs/{sha}/{name}` | workspace |

Uploads: max 50 MB; extensions `.pdf .docx .pptx .xlsx .png .jpg .jpeg .webp .tif .tiff` (else 415).

## Module boundaries
```
ingestion.loaders.load(filename, bytes) -> LoadedDocument(pages: render_png, text, images)
ingestion.structurer.structure(loaded, llm, model, usage, ...) -> SOPDocument
evaluation.engine.evaluate(doc, evidence, catalogue, llm, model, effort) -> EvaluationResult
  ├─ evaluation.assessor.Assessor.assess(...) -> list[CheckResult]      (LLM)
  ├─ scoring.scorer.score(catalogue, raw) -> overall, gate, dims, results (code)
  └─ scoring.improvements.overlay(...), improvements(...)               (code)
```
`services.py` wraps these with blob storage, the extraction cache and the result cache.

## Providers
`services.providers()` returns `AnthropicLLM` (real) or `ScriptedLLM` wrapping `ingestion/offline.py` + `evaluation/offline.py` when `SWC_LLM_PROVIDER=offline`. Offline results are labelled `offline:offline` in `engine.models`, and the UI shows an "offline demo" banner.

## Cost model
- Extraction: one vision call per `SWC_PAGES_PER_EXTRACTION_CALL` pages (default 4); cached by file hash.
- Evaluation: 12 calls for Core 1 (one per subcategory) over a cached prefix; +1 retry per subcategory only when a check is missing or a `met` quote fails verification. L2/L3 without evidence: 0 calls.
- Pricing table for cost reporting: `PRICING` in `app/llm/client.py`.
