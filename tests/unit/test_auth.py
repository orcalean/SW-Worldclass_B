import httpx
import pytest

from app.auth import hash_password, verify_password
from app.auth.seed import claim_orphans, deactivate, upsert
from app.jobs import runner
from tests.unit.test_ingestion import SOP_LINES, make_pdf


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


async def _login(c, email):
    upsert(email, "password-1")
    assert (await c.post("/v1/auth/login", json={"email": email, "password": "password-1"})).status_code == 200


async def _upload(c, **kw):
    r = await c.post("/v1/sops", files={"file": ("badge.pdf", make_pdf(SOP_LINES), "application/pdf")}, **kw)
    assert r.status_code == 202, r.text
    await runner.drain()
    return r.json()


async def test_sops_are_private_to_their_uploader(client):
    await _login(client, "alice@x.com")
    up = await _upload(client)
    sid = up["sop_id"]
    a = await client.post(f"/v1/sops/{sid}/revisions/1/assess")
    await runner.drain()
    aid = (await client.get(f"/v1/sops/{sid}")).json()["revisions"][0]["latest_assessment_id"]
    assert aid and a.status_code == 202
    assert [s["id"] for s in (await client.get("/v1/sops")).json()] == [sid]

    await client.post("/v1/auth/logout")
    await _login(client, "bob@x.com")
    assert (await client.get("/v1/sops")).json() == []
    for path in (f"/v1/sops/{sid}", f"/v1/sops/{sid}/revisions/1/document", f"/v1/assessments/{aid}"):
        assert (await client.get(path)).status_code == 404, path
    assert (await client.post(f"/v1/sops/{sid}/revisions/1/assess")).status_code == 404
    re_up = await client.post("/v1/sops", files={"file": ("x.pdf", make_pdf(SOP_LINES), "application/pdf")}, data={"sop_id": sid})
    assert re_up.status_code == 404

    # service callers (X-API-Key, no session) still see everything
    client.cookies.clear()
    svc = (await client.get("/v1/sops", headers={"X-API-Key": "svc-key"})).json()
    assert [s["id"] for s in svc] == [sid]


async def test_claim_orphans(client):
    await _upload(client, headers={"X-API-Key": "svc-key"})  # no session -> no owner
    await _login(client, "carol@x.com")
    assert (await client.get("/v1/sops")).json() == []
    assert claim_orphans("carol@x.com") == 1
    assert len((await client.get("/v1/sops")).json()) == 1
    assert claim_orphans("nobody@x.com") is None
