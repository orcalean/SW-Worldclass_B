# 0009. User login: FastAPI sessions in an HttpOnly cookie; seeded users

- Status: Accepted
- Date: 2026-10-27
- Decided by: owner (chose this over Auth.js via Express and Supabase Auth; wanted a NextAuth-like `useSession` in the UI)

## Context
The app is going onto a server and needs a login. The only protection was `X-API-Key`, whose UI copy (`VITE_API_KEY`) was readable in the browser bundle, and `<img>` tags couldn't send it. The owner asked for Auth.js, but Auth.js needs a JS server runtime (Next/SvelteKit/Express); the UI is a static Vite SPA and the API is FastAPI. Users should live in our own table and be seeded (no sign-up).

## Decision
- Tables `users` (email, name, scrypt password hash, is_active) and `user_sessions` (id = sha256 of the cookie token, user_id, expires_at); migration `19ee320bdd08`.
- `POST /v1/auth/login` sets cookie `swc_session` (HttpOnly, SameSite=Lax, `Secure` via `SWC_COOKIE_SECURE`, `SWC_SESSION_DAYS`, default 7). `POST /v1/auth/logout` deletes the session. `GET /v1/auth/me` returns `{user, auth_required}`.
- Every other `/v1` route (router dependency `require_auth`) accepts a valid session cookie **or** a valid `X-API-Key` (kept for service callers such as SWP).
- `SWC_AUTH_REQUIRED` (default true). False = old behaviour for local dev (open unless `SWC_API_KEYS` is set).
- Users are managed with `python -m app.auth.seed` (add / reset password / file / list / deactivate). Reset and deactivate end the user's sessions.
- UI: `src/auth/session.tsx` gives NextAuth-style `useSession()`, `signIn()`, `signOut()`, `<SessionProvider>`, `<RequireAuth>`; `VITE_API_KEY` removed.
- Password hashing uses stdlib `hashlib.scrypt` (no new dependency).

## Consequences
- No extra service; sessions survive refresh, restarts and redeploys (they're in the database) and can be revoked.
- `<img src="/v1/blobs/...">` works when logged in (the browser sends the cookie).
- UI and API must be same-site (same host via the dev proxy / reverse proxy) for the SameSite=Lax cookie. A cross-site `VITE_API_BASE` would need SameSite=None + HTTPS.
- Follow-ups: login rate limiting / lockout; roles and per-customer data isolation (all signed-in users see all data); self-service password change.
