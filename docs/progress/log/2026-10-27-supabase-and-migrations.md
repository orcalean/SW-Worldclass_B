# 2026-10-27 · Supabase + Alembic

**Why:** owner wanted to see the data (it was a SQLite file inside a broken Docker volume) and asked for Postgres via Supabase.

**Done**
- `DATABASE_URL` (pooler :6543, app) and `DIRECT_URL` (:5432, migrations) read from `.env`; Prisma-style URLs normalised in `app/config.py`.
- Alembic added (`alembic.ini`, `migrations/`); initial migration `d461aa2027bc` = the 6 existing tables. `create_all` removed; `app/storage/migrate.py` upgrades on first connect and stamps pre-Alembic SQLite files.
- Engine for Postgres: `pool_pre_ping`, `prepare_threshold=None` (transaction pooler).
- Tests forced onto temp SQLite (fixes the "tests can touch a real DB" known issue).
- Migrated Supabase (eu-north-1): 6 tables + `alembic_version`; write/read/delete smoke test via the pooler passed; test row removed.
- ADR 0008; CLAUDE.md, `.env.example`, data-model doc updated.

- Docker image now copies `alembic.ini` + `migrations/` (startup crashed without them); alembic plugin log noise silenced.
- Copied all rows from the Docker volume's old SQLite (`/data/swc.db`: 5 SOPs, 5 revisions, 3 assessments, 3 extraction cache, 8 jobs) into Supabase in one transaction. Blobs stay in the `swc-data` volume; their `blob://` URIs still resolve.
- Docker compose (api + ui) verified working against Supabase.

**Not done / next**
- Blobs still local (volume). Owner decision pending on Supabase Storage.
