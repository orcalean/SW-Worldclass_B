# 2026-10-27 · User login

**Why:** owner is deploying to a server and asked for a login page with seeded users (asked for Auth.js; chose FastAPI sessions after the stack mismatch was explained, ADR 0009).

**Done**
- `users` + `user_sessions` tables (migration `19ee320bdd08`), scrypt hashes, HttpOnly `swc_session` cookie.
- `/v1/auth/login|logout|me`; `require_auth` replaces `require_key` (cookie OR X-API-Key; `SWC_AUTH_REQUIRED=false` for open local dev).
- Seed CLI `python -m app.auth.seed` (add / reset / file / list / deactivate).
- Frontend: `/login`, `useSession`/`signIn`/`signOut`, route guard, header user + sign out; `VITE_API_KEY` removed. Blob images now load (cookie is sent).
- 5 new tests (34 pass); end-to-end curl through the Vite proxy passed.

**Not done / next**
- Migration not yet applied to Supabase (happens on next API start).
- No users seeded on the real DB yet. Not clicked through in a browser.
- Rate limiting, roles, password change (see auth-and-access.md).
