# Data model

SQLAlchemy models in `app/storage/db.py`. Database: **Supabase Postgres** via `DATABASE_URL` / `DIRECT_URL` (ADR 0008); without them, SQLite at `<SWC_DATA_DIR>/swc.db`.

Schema changes go through **Alembic** (`migrations/versions/`). The app runs `alembic upgrade head` on first connect (`app/storage/migrate.py`, using `DIRECT_URL`); a pre-Alembic SQLite file (tables but no `alembic_version`) is stamped as the initial revision so its data is kept. To change the schema: edit the models, then `uv run alembic revision --autogenerate -m "<what>"`, review the generated file, commit it.

```mermaid
erDiagram
  SOP ||--o{ REVISION : has
  REVISION ||--o{ EVIDENCE : has
  REVISION ||--o{ ASSESSMENT : has
  SOP { string id PK; string name; string plant; string line; string station; datetime created_at }
  REVISION { string id PK; string sop_id FK; int number; string filename; string sha256; string status; json document; datetime created_at }
  EVIDENCE { string id PK; string revision_id FK; json item; datetime created_at }
  ASSESSMENT { string id PK; string revision_id FK "nullable"; string cache_key; float score; string status; json result; datetime created_at }
  EXTRACTION_CACHE { string key PK; json document; float cost_usd }
  USER ||--o{ USER_SESSION : has
  USER { string id PK; string email UK; string name; string password_hash; bool is_active; datetime created_at }
  USER_SESSION { string id PK "sha256(token)"; string user_id FK; datetime created_at; datetime expires_at }
  JOB { string id PK; string kind; string status; string stage; text error; string result_type; string result_id; json result; datetime created_at; datetime updated_at }
```

| Model | Table | Notes |
|---|---|---|
| `SOP` | `sops` | One per standard (station/operation). Revisions ordered by `number`. |
| `Revision` | `revisions` | One per upload. `status`: `ingesting` → `extracted` → `reviewed` (after PUT document), or `failed`. `document` = `SOPDocument` JSON. |
| `Evidence` | `evidence` | `item` = `EvidenceItem` JSON (level L2/L3). |
| `Assessment` | `assessments` | `result` = `EvaluationResult` JSON. `revision_id` is null for stateless `/v1/evaluate` calls. `cache_key` = `engine.cache_key(...)`; a cache hit for another revision creates a new row with the same result. |
| `ExtractionCache` | `extraction_cache` | key = sha256(file sha + `EXTRACT_PROMPT_VERSION` + provider + model). |
| `User` | `users` | Login accounts (ADR 0009), seeded via `python -m app.auth.seed`. Email unique, lower-case; scrypt `password_hash`; `is_active=false` blocks login. |
| `UserSession` | `user_sessions` | One per login; `id` = sha256 of the `swc_session` cookie token; fixed `expires_at`. Deleted on logout / password reset / deactivation. |
| `Job` | `jobs` | `status`: queued / running / succeeded / failed. `result` holds inline output for black-box calls. Running jobs are marked failed on restart (`runner.recover_interrupted`). |

## Blobs
`Blobs` stores files content-addressed under `<SWC_DATA_DIR>/blobs/<sha256>/<name>` and exposes them as `blob://<sha>/<name>` URIs, served by `GET /v1/blobs/{sha}/{name}` (path traversal guarded in `Blobs.path`). Stored per upload: `source.<ext>`, `page-<n>.png` renders, `p<n>-img<k>.png` embedded images; evidence as `evidence.<ext>`.

Ph2 note: SWP keeps text + images and builds PDFs at runtime; `SOPDocument` + blob URIs mirror that shape so no PDF is required for evaluation.
