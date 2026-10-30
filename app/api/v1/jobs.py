"""Black-box (stateless) endpoints any app can use.

  POST /v1/ingest      file -> job -> SOPDocument
  POST /v1/evaluate    {sop_document, evidence[]} -> job -> EvaluationResult   (Ph2 SWP entry point)
  GET  /v1/jobs/{id}   status + inline result (also polled for workspace jobs)
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import services
from app.api.v1.common import JobOut, JobRef, job_out, read_upload
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.jobs import runner
from app.storage import db

router = APIRouter(tags=["jobs"])


class EvaluateIn(BaseModel):
    sop_document: SOPDocument
    evidence: list[EvidenceItem] = Field(default_factory=list)


@router.post("/ingest", response_model=JobRef, status_code=202)
async def ingest(file: UploadFile = File(...)) -> JobRef:
    data = await read_upload(file)
    name = file.filename or "upload"

    async def work(stage):
        stage("extracting")
        doc, _ = await services.ingest_bytes(name, data)
        return "sop_document", None, doc.model_dump(mode="json", by_alias=True)

    return JobRef(job_id=runner.submit("ingest", work))


@router.post("/evaluate", response_model=JobRef, status_code=202)
async def evaluate(body: EvaluateIn) -> JobRef:
    async def work(stage):
        stage("evaluating")
        aid, res = await services.assess(body.sop_document, body.evidence)
        return "assessment", aid, res.model_dump(mode="json")

    return JobRef(job_id=runner.submit("evaluate", work))


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: str) -> JobOut:
    with db.session() as ses:
        j = ses.get(db.Job, job_id)
        if not j:
            raise HTTPException(404, "job not found")
        return job_out(j)
