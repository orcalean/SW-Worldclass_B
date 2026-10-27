# Auth and access

## Current state
- **No user login, no roles, no tenants.** The UI's "Signed in · Quality / Process" label is static text from the design (frontend repo `src/components/Shell.tsx`).
- **API key (optional):** if `SWC_API_KEYS` (comma-separated) is set in `.env`, every `/v1` route requires header `X-API-Key` with one of the keys. Implemented by the router dependency `require_key` in `app/api/v1/routes.py`. Empty = auth off (local dev).
- The frontend sends `X-API-Key` from `VITE_API_KEY` (frontend repo `src/api/client.ts`) on `fetch` calls only.
- CORS origins: `SWC_CORS_ORIGINS` (default `http://localhost:5173`), in `app/main.py`.

## Known gaps
- `VITE_API_KEY` is compiled into the JS bundle, so it is readable by anyone using the UI.
- `<img>` tags cannot send the header, so images from `/v1/blobs` fail when keys are enabled.
- All data is visible to every caller with a valid key; no per-customer isolation.

## Rules until real auth exists
- Treat the API key as a service-to-service credential (e.g. SWP → this API), not a user credential.
- Any login, role or tenant design is an owner decision: ask, then record an ADR.
