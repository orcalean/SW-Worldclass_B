# 0008. Supabase Postgres for the database; Alembic for migrations

- Status: Accepted
- Date: 2026-10-27
- Decided by: owner (chose Supabase over MongoDB; Postgres recommended)

## Context
Data lived in a SQLite file inside a Docker volume: hard to inspect, single-user, and the schema was created with `create_all` (no migrations, so adding a column would break existing databases). The data is relational (SOP → revisions → evidence / assessments, jobs), with large JSON documents for the extracted SOP and results. MongoDB was considered; Postgres JSON columns cover the document part without rewriting storage.

## Decision
- Database: Supabase Postgres. The app connects with `DATABASE_URL` (transaction pooler, :6543; prepared statements disabled); migrations use `DIRECT_URL` (:5432). Prisma-style URLs are accepted as-is (`app/config.py` → `sqlalchemy_url`). SQLite remains the default when no URL is set (local dev, tests).
- ORM stays SQLAlchemy. Migrations: Alembic in `migrations/`; the app upgrades to head on first connect.
- Tests always use a temp SQLite file (`tests/conftest.py` sets `SWC_DATABASE_URL`), never the `.env` database.
- Uploaded files (blobs) stay on local disk for now.

## Consequences
- Data is visible in Supabase's Table Editor; several users/instances can share one database.
- Every model change needs a reviewed migration file committed with it.
- Follow-ups (owner decisions): Supabase Storage for blobs; Supabase Auth for user logins (would replace the exposed `VITE_API_KEY`); region choice for customer data (currently eu-north-1).
