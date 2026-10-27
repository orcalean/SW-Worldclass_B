import pytest


@pytest.fixture
def offline_env(tmp_path, monkeypatch):
    """Fresh data dir + offline LLM provider; clears cached settings/DB between tests."""
    from app import config
    from app.storage import db

    monkeypatch.setenv("SWC_LLM_PROVIDER", "offline")
    monkeypatch.setenv("SWC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SWC_API_KEYS", "")
    config.get_settings.cache_clear()
    db._sessionmaker.cache_clear()
    yield tmp_path
    config.get_settings.cache_clear()
    db._sessionmaker.cache_clear()
