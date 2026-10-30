import httpx
import pytest

from app.auth import hash_password, verify_password
from app.auth.seed import deactivate, upsert


@pytest.fixture
async def client(offline_env, monkeypatch):
    from app import config
    from app.main import app

    monkeypatch.setenv("SWC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SWC_API_KEYS", "svc-key")
    config.get_settings.cache_clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


def test_password_hash_roundtrip():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")


async def test_login_session_logout(client):
    upsert("Alice@Plant.com", "s3cret-pass", "Alice")
    assert (await client.get("/v1/sops")).status_code == 401
    me = (await client.get("/v1/auth/me")).json()
    assert me == {"user": None, "auth_required": True}

    bad = await client.post("/v1/auth/login", json={"email": "alice@plant.com", "password": "nope"})
    assert bad.status_code == 401
    assert (await client.post("/v1/auth/login", json={"email": "bob@x.com", "password": "nope"})).status_code == 401

    r = await client.post("/v1/auth/login", json={"email": " ALICE@plant.com", "password": "s3cret-pass"})
    assert r.status_code == 200 and r.json()["email"] == "alice@plant.com"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert (await client.get("/v1/sops")).status_code == 200
    assert (await client.get("/v1/auth/me")).json()["user"]["name"] == "Alice"

    assert (await client.post("/v1/auth/logout")).status_code == 204
    assert (await client.get("/v1/sops")).status_code == 401


async def test_api_key_still_works(client):
    assert (await client.get("/v1/sops", headers={"X-API-Key": "svc-key"})).status_code == 200
    assert (await client.get("/v1/sops", headers={"X-API-Key": "other"})).status_code == 401


async def test_deactivate_and_password_reset_end_sessions(client):
    upsert("a@x.com", "password-1")
    await client.post("/v1/auth/login", json={"email": "a@x.com", "password": "password-1"})
    assert (await client.get("/v1/sops")).status_code == 200
    upsert("a@x.com", "password-2")  # reset logs out everywhere
    assert (await client.get("/v1/sops")).status_code == 401

    await client.post("/v1/auth/login", json={"email": "a@x.com", "password": "password-2"})
    assert deactivate("a@x.com")
    assert (await client.get("/v1/sops")).status_code == 401
    r = await client.post("/v1/auth/login", json={"email": "a@x.com", "password": "password-2"})
    assert r.status_code == 401


def test_seed_rejects_short_password(offline_env):
    with pytest.raises(ValueError):
        upsert("a@x.com", "short")
