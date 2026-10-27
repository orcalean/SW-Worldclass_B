import pytest


@pytest.fixture
def offline_env(tmp_path, monkeypatch):
    """Fresh data dir + offline LLM provider; clears cached settings/DB between tests."""
    from app import config
    from app.storage import db

    monkeypatch.setenv("SWC_LLM_PROVIDER", "offline")
    monkeypatch.setenv("SWC_DATA_DIR", str(tmp_path))
    # Never touch the real database from .env (e.g. Supabase): force a throwaway SQLite file.
    monkeypatch.setenv("SWC_DATABASE_URL", f"sqlite:///{tmp_path / 'swc.db'}")
    monkeypatch.setenv("DIRECT_URL", "")
    monkeypatch.setenv("SWC_API_KEYS", "")
    config.get_settings.cache_clear()
    db._sessionmaker.cache_clear()
    yield tmp_path
    config.get_settings.cache_clear()
    db._sessionmaker.cache_clear()
