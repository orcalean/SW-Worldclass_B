"""v1 API.

Black-box (stateless) endpoints any app can use:
  POST /v1/ingest            file -> job -> SOPDocument
  POST /v1/evaluate          {sop_document, evidence[]} -> job -> EvaluationResult   (Ph2 SWP entry point)
  GET  /v1/jobs/{id}         status + inline result
  GET  /v1/rubrics[/{id}]    rubric catalogue

Workspace (stateful) endpoints used by the sw-world-class UI:
  /v1/sops, revisions (re-upload), extraction review (PATCH document), evidence, assessments, blobs
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.contracts.evaluation import EvaluationResult
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.ingestion.loaders import SUPPORTED
from app.jobs import runner
from app.rubric.registry import load_catalogue
from app import services
from app.storage import db

MAX_UPLOAD = 50 * 1024 * 1024


def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    keys = {k.strip() for k in get_settings().api_keys.split(",") if k.strip()}
    if keys and x_api_key not in keys:
        raise HTTPException(401, "invalid or missing X-API-Key")


router = APIRouter(prefix="/v1", dependencies=[Depends(require_key)])


# ---------- schemas ----------
class JobRef(BaseModel):
    job_id: str
    status: str = "queued"


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str | None
    error: str | None
    result_type: str | None
    result_id: str | None
    result: dict | None = Field(None, description="Inline SOPDocument / EvaluationResult for stateless calls")


class EvaluateIn(BaseModel):
    sop_document: SOPDocument
    evidence: list[EvidenceItem] = Field(default_factory=list)


class RevisionOut(BaseModel):
    id: str
    number: int
    filename: str | None
    status: str
    created_at: str
    evidence: list[EvidenceItem]
    latest_assessment_id: str | None
    score: float | None
    benchmark_status: str | None
    gate: str | None
    extraction_warnings: list[str]


class SOPOut(BaseModel):
    id: str
    name: str
    plant: str | None
    line: str | None
    station: str | None
    revisions: list[RevisionOut]


class UploadOut(BaseModel):
    sop_id: str
    revision_id: str
    revision: int
    job_id: str


class AssessOut(BaseModel):
    job_id: str


# ---------- helpers ----------
async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file exceeds {MAX_UPLOAD // 1024 // 1024} MB")
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in SUPPORTED:
        raise HTTPException(415, f"unsupported type {suffix}; supported: {sorted(SUPPORTED)}")
    return data


def _job_out(j: db.Job) -> JobOut:
    return JobOut(id=j.id, kind=j.kind, status=j.status, stage=j.stage, error=j.error,
                  result_type=j.result_type, result_id=j.result_id, result=j.result)


def _revision_out(r: db.Revision) -> RevisionOut:
    a = r.assessments[-1] if r.assessments else None
    doc = r.document or {}
    return RevisionOut(
        id=r.id, number=r.number, filename=r.filename, status=r.status, created_at=r.created_at.isoformat(),
        evidence=[EvidenceItem.model_validate(e.item) for e in r.evidence],
        latest_assessment_id=a.id if a else None, score=a.score if a else None,
        benchmark_status=a.status if a else None,
        gate=(a.result.get("gate") or {}).get("status") if a else None,
        extraction_warnings=doc.get("extraction_warnings", []),
    )


def _sop_out(s: db.SOP) -> SOPOut:
    return SOPOut(id=s.id, name=s.name, plant=s.plant, line=s.line, station=s.station,
                  revisions=[_revision_out(r) for r in s.revisions])


def _get_revision(ses, sop_id: str, number: int) -> db.Revision:
    r = ses.query(db.Revision).filter_by(sop_id=sop_id, number=number).first()
    if not r:
        raise HTTPException(404, "revision not found")
    return r


# ---------- black-box ----------
@router.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    p = services.providers(s)
    return {"status": "ok", "llm_provider": s.llm_provider,
            "models": {"extraction": p.extraction_model, "evaluation": p.evaluation_model}}


@router.get("/rubrics")
def rubrics() -> dict[str, Any]:
    cat = load_catalogue()
    return {
        "policy": cat.policy.model_dump(),
        "dimensions": [{"key": d.key, "name": d.name, "cores": [
            {"id": f"{d.key}.core{c.number}", "number": c.number, "name": c.name, "assessed": c.core is not None,
             "version": c.core.version if c.core else None,
             "checks": len(c.core.checks()) if c.core else 0} for c in d.cores]} for d in cat.dimensions],
    }


@router.get("/rubrics/{core_id}")
def rubric(core_id: str) -> dict[str, Any]:
    for core in load_catalogue().assessed_cores():
        if core.id == core_id:
            return core.model_dump()
    raise HTTPException(404, "rubric not found or not yet assessed")


@router.post("/ingest", response_model=JobRef, status_code=202)
async def ingest(file: UploadFile = File(...)) -> JobRef:
    data = await _read(file)
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
        return _job_out(j)


# ---------- workspace ----------
@router.get("/sops", response_model=list[SOPOut])
def list_sops() -> list[SOPOut]:
    with db.session() as ses:
        return [_sop_out(s) for s in ses.query(db.SOP).order_by(db.SOP.created_at.desc()).all()]


@router.get("/sops/{sop_id}", response_model=SOPOut)
def get_sop(sop_id: str) -> SOPOut:
    with db.session() as ses:
        s = ses.get(db.SOP, sop_id)
        if not s:
            raise HTTPException(404, "SOP not found")
        return _sop_out(s)


@router.post("/sops", response_model=UploadOut, status_code=202)
async def upload_sop(
    file: UploadFile = File(...),
    sop_id: str | None = Form(None, description="Existing SOP id to add a new revision (re-upload)"),
    name: str | None = Form(None), plant: str | None = Form(None), line: str | None = Form(None),
    station: str | None = Form(None),
) -> UploadOut:
    data = await _read(file)
    fname = file.filename or "upload"
    with db.session() as ses:
        if sop_id:
            sop = ses.get(db.SOP, sop_id)
            if not sop:
                raise HTTPException(404, "SOP not found")
        else:
            sop = db.SOP(name=name or fname.rsplit(".", 1)[0], plant=plant, line=line, station=station)
            ses.add(sop)
            ses.flush()
        number = (max((r.number for r in sop.revisions), default=0)) + 1
        rev = db.Revision(sop_id=sop.id, number=number, filename=fname)
        ses.add(rev)
        ses.commit()
        sop_id_, rev_id = sop.id, rev.id

    async def work(stage):
        stage("extracting")
        try:
            doc, _ = await services.ingest_bytes(fname, data)
        except Exception:
            _set_rev(rev_id, status="failed")
            raise
        _set_rev(rev_id, status="extracted", document=doc.model_dump(mode="json", by_alias=True),
                 sha256=doc.source.sha256)
        return "revision", rev_id, None

    return UploadOut(sop_id=sop_id_, revision_id=rev_id, revision=number, job_id=runner.submit("ingest", work))


def _set_rev(rev_id: str, **fields) -> None:
    with db.session() as ses:
        r = ses.get(db.Revision, rev_id)
        for k, v in fields.items():
            setattr(r, k, v)
        ses.commit()


@router.get("/sops/{sop_id}/revisions/{number}/document", response_model=SOPDocument)
def get_document(sop_id: str, number: int) -> SOPDocument:
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number)
        if not r.document:
            raise HTTPException(409, f"revision is {r.status}; no document yet")
        return SOPDocument.model_validate(r.document)


@router.put("/sops/{sop_id}/revisions/{number}/document", response_model=SOPDocument)
def put_document(sop_id: str, number: int, doc: SOPDocument) -> SOPDocument:
    """Human-reviewed extraction replaces the machine one; scoring uses this version."""
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number)
        if r.status in ("ingesting", "failed"):
            raise HTTPException(409, f"revision is {r.status}")
        for i, we in enumerate(sorted(doc.work_elements, key=lambda w: w.seq), start=1):
            we.seq = i
        r.document = doc.model_dump(mode="json", by_alias=True)
        r.status = "reviewed"
        ses.commit()
        return doc


@router.post("/sops/{sop_id}/revisions/{number}/evidence", response_model=EvidenceItem, status_code=201)
async def add_evidence(sop_id: str, number: int, file: UploadFile = File(...),
                       level: str = Form(..., pattern="^L[23]$"), kind: str = Form("document"),
                       title: str | None = Form(None)) -> EvidenceItem:
    data = await _read(file)
    with db.session() as ses:
        rev_id = _get_revision(ses, sop_id, number).id
    item = await services.evidence_from_bytes(file.filename or "evidence", data, level, kind, title)
    with db.session() as ses:
        ses.add(db.Evidence(revision_id=rev_id, item=item.model_dump(mode="json")))
        ses.commit()
    return item


@router.delete("/sops/{sop_id}/revisions/{number}/evidence/{evidence_id}", status_code=204)
def delete_evidence(sop_id: str, number: int, evidence_id: str) -> None:
    with db.session() as ses:
        rev = _get_revision(ses, sop_id, number)
        for e in rev.evidence:
            if e.item.get("id") == evidence_id:
                ses.delete(e)
        ses.commit()


@router.post("/sops/{sop_id}/revisions/{number}/assess", response_model=AssessOut, status_code=202)
async def assess_revision(sop_id: str, number: int) -> AssessOut:
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number)
        if not r.document:
            raise HTTPException(409, f"revision is {r.status}; nothing to assess")
        doc = SOPDocument.model_validate(r.document)
        evidence = [EvidenceItem.model_validate(e.item) for e in r.evidence]
        rev_id = r.id

    async def work(stage):
        stage("evaluating")
        aid, _ = await services.assess(doc, evidence, revision_id=rev_id)
        return "assessment", aid, None

    return AssessOut(job_id=runner.submit("evaluate", work))


@router.get("/assessments/{assessment_id}", response_model=EvaluationResult)
def get_assessment(assessment_id: str) -> EvaluationResult:
    with db.session() as ses:
        a = ses.get(db.Assessment, assessment_id)
        if not a:
            raise HTTPException(404, "assessment not found")
        return EvaluationResult.model_validate(a.result)


@router.get("/blobs/{sha}/{name}")
def blob(sha: str, name: str) -> FileResponse:
    p = db.Blobs().path(sha, name)
    if p is None:
        raise HTTPException(404, "not found")
    return FileResponse(p)
