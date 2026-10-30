# 0010. SOPs are private to the user who uploaded them

- Status: Accepted
- Date: 2026-10-30
- Decided by: owner

## Context
With login (ADR 0009) every signed-in user saw every SOP. The owner wants each uploaded SOP mapped to the logged-in user, and each user to see only their own. SOPs uploaded before this change have no uploader.

## Decision
- `sops.owner_id` → `users.id` (nullable, `ON DELETE SET NULL`), migration `7c41e2a9b3d5`. `POST /v1/sops` sets it from the session user.
- A request with a session cookie only sees SOPs it owns: `GET /v1/sops` filters; every `/v1/sops/{id}/…` route (detail, re-upload, document, evidence, assess) and `GET /v1/assessments/{id}` for a revision's assessment return **404** for anyone else (no hint that the id exists).
- Requests without a user see all SOPs: `X-API-Key` service callers and login-off local dev. Their uploads get `owner_id = NULL`.
- Existing / API-key SOPs (`owner_id` NULL) are invisible to signed-in users until assigned: `python -m app.auth.seed <email> --claim-orphans`.
- Black-box endpoints (`/v1/ingest`, `/v1/evaluate`, `/v1/jobs/{id}`) and their results stay unscoped: no SOP is stored, ids are random.

## Consequences
Users can't see each other's work; there is no sharing yet (no teams/roles). `GET /v1/jobs/{id}` and `GET /v1/blobs/{sha}/{name}` are not scoped by user; they rely on unguessable ids (job ids, content hashes). Add `jobs.user_id` / blob ownership if that becomes a requirement.
