from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    database_url: str = ""  # default: sqlite file under data_dir
    api_keys: str = ""  # comma-separated; empty disables auth (local dev)
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
