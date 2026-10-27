from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # backend/.env is found regardless of the working directory; real env vars take precedence.
    model_config = SettingsConfigDict(env_prefix="SWC_", env_file=BACKEND_DIR / ".env", extra="ignore")

    # Read without the SWC_ prefix so the standard variable name works.
    anthropic_api_key: str = Field("", validation_alias="ANTHROPIC_API_KEY")

    # "anthropic" for real runs; "offline" uses the deterministic heuristic provider (no API key, demo/tests only)
    llm_provider: str = "anthropic"
    extraction_model: str = "claude-sonnet-5-5"
    evaluation_model: str = "claude-sonnet-5-5"
    cheap_model: str = "claude-haiku-5-5"
    extraction_effort: str = "low"
    evaluation_effort: str = "medium"
    refusal_fallback: bool = True
    max_concurrency: int = 6
    pages_per_extraction_call: int = 4

    data_dir: Path = Path("./data")
    database_url: str = ""  # SWC_DATABASE_URL: explicit override (tests use it); wins over DATABASE_URL
    # Supabase / Prisma-style names, read without the SWC_ prefix:
    # DATABASE_URL = pooled connection the app uses; DIRECT_URL = direct/session connection for migrations.
    pooled_database_url: str = Field("", validation_alias="DATABASE_URL")
    direct_database_url: str = Field("", validation_alias="DIRECT_URL")
    api_keys: str = ""  # comma-separated; empty disables auth (local dev)
    cors_origins: str = "http://localhost:5173"

    def db_url(self) -> str:
        """URL the app connects with. Default: SQLite file under data_dir."""
        url = self.database_url or self.pooled_database_url
        return sqlalchemy_url(url) if url else f"sqlite:///{(self.data_dir / 'swc.db').resolve()}"

    def migration_db_url(self) -> str:
        """URL migrations run with: DIRECT_URL when set (poolers in transaction mode can't run DDL safely)."""
        if self.database_url:
            return sqlalchemy_url(self.database_url)
        return sqlalchemy_url(self.direct_database_url) if self.direct_database_url else self.db_url()


def sqlalchemy_url(url: str) -> str:
    """Accept plain postgres URLs (Supabase/Prisma style): use the psycopg 3 driver and drop Prisma-only params."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("pgbouncer", "connection_limit")]
    return urlunsplit(parts._replace(query=urlencode(query)))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
