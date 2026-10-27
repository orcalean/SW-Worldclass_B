import json
from pathlib import Path

import httpx
import pytest

from app.jobs import runner
from tests.unit.test_ingestion import SOP_LINES, make_pdf

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/badge_sop.json").read_text())


@pytest.fixture
async def client(offline_env):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def wait(c, job_id):
    await runner.drain()
    j = (await c.get(f"/v1/jobs/{job_id}")).json()
    assert j["status"] == "succeeded", j
    return j


async def test_blackbox_evaluate_with_structured_document(client):
    r = await client.post("/v1/evaluate", json={"sop_document": FIXTURE, "evidence": []})
    assert r.status_code == 202
    j = await wait(client, r.json()["job_id"])
    res = j["result"]
    assert res["gate"]["status"] == "blocked"
    assert res["engine"]["models"]["evaluation"] == "offline:offline"
    # identical input -> cached, identical result
    r2 = await client.post("/v1/evaluate", json={"sop_document": FIXTURE, "evidence": []})
    j2 = await wait(client, r2.json()["job_id"])
    assert j2["result"]["usage"]["cached_result"] is True
    assert j2["result"]["overall"] == res["overall"]


async def test_blackbox_ingest(client):
    r = await client.post("/v1/ingest", files={"file": ("badge.pdf", make_pdf(SOP_LINES), "application/pdf")})
    j = await wait(client, r.json()["job_id"])
    assert len(j["result"]["work_elements"]) == 5


async def test_workspace_upload_review_evidence_assess_reupload(client):
    r = await client.post("/v1/sops", files={"file": ("badge.pdf", make_pdf(SOP_LINES), "application/pdf")},
                          data={"plant": "Chicago", "line": "Trim 1", "station": "1955L"})
    up = r.json()
    await wait(client, up["job_id"])
    sid = up["sop_id"]

    doc = (await client.get(f"/v1/sops/{sid}/revisions/1/document")).json()
    assert doc["meta"]["revision"] == "7"
    # human review: fix the force spec
    doc["work_elements"][3]["specs"] = [{"characteristic": "application force", "value": "40", "unit": "N",
                                        "tolerance": "5", "direction": "range"}]
    doc["work_elements"][3]["steps"][0]["text"] = "Apply badge with 40 ± 5 N, minimum hold 5 s"
    assert (await client.put(f"/v1/sops/{sid}/revisions/1/document", json=doc)).status_code == 200

    ev = await client.post(f"/v1/sops/{sid}/revisions/1/evidence",
                           files={"file": ("station.png", _png(), "image/png")}, data={"level": "L2", "kind": "photo"})
    assert ev.status_code == 201 and ev.json()["level"] == "L2"

    a = await client.post(f"/v1/sops/{sid}/revisions/1/assess")
    await wait(client, a.json()["job_id"])
    sop = (await client.get(f"/v1/sops/{sid}")).json()
    rev1 = sop["revisions"][0]
    assert rev1["status"] == "reviewed" and rev1["score"] is not None and rev1["evidence"]
    res = (await client.get(f"/v1/assessments/{rev1['latest_assessment_id']}")).json()
    assert "Q01-3-01" not in res["gate"]["blocking"]

    # re-upload creates revision 2 under the same SOP
    r2 = await client.post("/v1/sops", files={"file": ("badge_v2.pdf", make_pdf(SOP_LINES[:5]), "application/pdf")},
                           data={"sop_id": sid})
    assert r2.json()["revision"] == 2
    await wait(client, r2.json()["job_id"])
    assert [x["number"] for x in (await client.get(f"/v1/sops/{sid}")).json()["revisions"]] == [1, 2]


async def test_rejects_unsupported_and_unknown(client):
    r = await client.post("/v1/ingest", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert (await client.get("/v1/assessments/nope")).status_code == 404
    rub = (await client.get("/v1/rubrics")).json()
    q = next(d for d in rub["dimensions"] if d["key"] == "Q")
    assert q["cores"][0]["checks"] == 56


async def test_api_key_enforced(client, monkeypatch):
    from app import config

    monkeypatch.setenv("SWC_API_KEYS", "k1,k2")
    config.get_settings.cache_clear()
    assert (await client.get("/v1/health")).status_code == 401
    assert (await client.get("/v1/health", headers={"X-API-Key": "k2"})).status_code == 200


def _png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 120, 120)).save(buf, "PNG")
    return buf.getvalue()
