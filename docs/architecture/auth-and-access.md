# Auth and access

User login per ADR 0009. Code: `app/auth/__init__.py` (hashing, sessions, `require_auth`), `app/auth/seed.py` (user CLI), `app/api/v1/auth.py` (endpoints).

## How a request is authorised
Every `/v1` route except `/v1/auth/*` has the router dependency `require_auth`, which allows the request if **any** of:
1. `X-API-Key` matches one of `SWC_API_KEYS` (service-to-service, e.g. SWP → this API);
2. the `swc_session` cookie maps to an unexpired session of an active user;
3. login is off: `SWC_AUTH_REQUIRED=false` **and** `SWC_API_KEYS` empty (local dev only).

Otherwise `401`.

## What each caller can see (ADR 0010)
- **Signed-in user (session cookie):** only SOPs they uploaded (`sops.owner_id`). `GET /v1/sops` is filtered; any other SOP id, its revisions, document, evidence, assess and its assessments return `404`. `app/auth.current_user` + `visible()` / `_get_sop()` in `app/api/v1/sops.py`.
- **`X-API-Key` caller or login off:** all SOPs; uploads get no owner.
- **SOPs with no owner** (uploaded before ADR 0010 or via API key) are invisible to users until claimed: `python -m app.auth.seed <email> --claim-orphans`.
- Not scoped: black-box `/v1/ingest`, `/v1/evaluate`, `/v1/jobs/{id}`, and `/v1/blobs/{sha}/{name}` (random ids / content hashes).

## Login flow
- `POST /v1/auth/login {email, password}` → checks the scrypt hash (email is trimmed + lower-cased; unknown emails still cost one hash so timing doesn't reveal them) → creates a `user_sessions` row → sets cookie `swc_session` (HttpOnly, SameSite=Lax, `Secure` when `SWC_COOKIE_SECURE=true`, max-age `SWC_SESSION_DAYS`). The DB stores only sha256(token).
- `GET /v1/auth/me` → `{user | null, auth_required}`. The UI calls it on every page load, so a refresh keeps the user signed in.
- `POST /v1/auth/logout` → deletes the session row and the cookie.
- Sessions have a fixed expiry (no sliding renewal). Expired rows for a user are cleaned up at their next login.

## Managing users (no sign-up page)
```bash
uv run python -m app.auth.seed alice@plant.com --name "Alice"      # add or reset password (prompts)
uv run python -m app.auth.seed alice@plant.com --password '...'     # non-interactive
uv run python -m app.auth.seed --file users.json                   # [{"email","name","password"}, ...]
uv run python -m app.auth.seed --list
uv run python -m app.auth.seed alice@plant.com --deactivate
uv run python -m app.auth.seed alice@plant.com --claim-orphans    # SOPs with no uploader -> alice
```
Uses the database from `.env`. Passwords ≥ 8 chars. A reset or deactivation ends all of that user's sessions. In Docker: `docker compose exec api uv run --no-dev python -m app.auth.seed ...`.

## Deploying
- Set `SWC_COOKIE_SECURE=true` behind HTTPS.
- Serve the UI and `/v1` from the same site (reverse proxy) so the cookie is sent; CORS has `allow_credentials` for a cross-origin but same-site UI (`SWC_CORS_ORIGINS` must list it).

## Known gaps
- No rate limiting / lockout on login.
- No roles, teams or sharing: each user sees only their own SOPs (ADR 0010).
- Jobs and blobs are not scoped by user (unguessable ids).
- No self-service password change (admin resets via the CLI).
