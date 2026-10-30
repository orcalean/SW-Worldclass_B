"""Workspace (stateful) endpoints used by the sw-world-class UI.

  GET/POST /v1/sops                                         list / upload (new SOP or re-upload as a revision)
  GET      /v1/sops/{id}                                    one SOP with its revisions
  GET/PUT  /v1/sops/{id}/revisions/{n}/document             extraction review
  POST     /v1/sops/{id}/revisions/{n}/evidence             add L2/L3 evidence
  DELETE   /v1/sops/{id}/revisions/{n}/evidence/{eid}
  POST     /v1/sops/{id}/revisions/{n}/assess               job -> assessment

Access (ADR 0010): a signed-in user only sees SOPs they uploaded; anything else is 404. X-API-Key callers and
login-off dev see every SOP.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import services
from app.api.v1.common import read_upload
from app.auth import current_user
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.jobs import runner
from app.storage import db

router = APIRouter(prefix="/sops", tags=["sops"])

Me = Annotated[db.User | None, Depends(current_user)]


# ---------- schemas ----------
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


def visible(user: db.User | None, sop: db.SOP | None) -> bool:
    """Signed-in users see their own SOPs; API-key callers and login-off dev see all."""
    return sop is not None and (user is None or sop.owner_id == user.id)


def _get_sop(ses, sop_id: str, user: db.User | None) -> db.SOP:
    s = ses.get(db.SOP, sop_id)
    if not visible(user, s):
        raise HTTPException(404, "SOP not found")
    return s


def _get_revision(ses, sop_id: str, number: int, user: db.User | None) -> db.Revision:
    _get_sop(ses, sop_id, user)
    r = ses.query(db.Revision).filter_by(sop_id=sop_id, number=number).first()
    if not r:
        raise HTTPException(404, "revision not found")
    return r


def _set_rev(rev_id: str, **fields) -> None:
    with db.session() as ses:
        r = ses.get(db.Revision, rev_id)
        for k, v in fields.items():
            setattr(r, k, v)
        ses.commit()


# ---------- endpoints ----------
@router.get("", response_model=list[SOPOut])
def list_sops(user: Me) -> list[SOPOut]:
    with db.session() as ses:
        q = ses.query(db.SOP)
        if user is not None:
            q = q.filter(db.SOP.owner_id == user.id)
        return [_sop_out(s) for s in q.order_by(db.SOP.created_at.desc()).all()]


@router.get("/{sop_id}", response_model=SOPOut)
def get_sop(sop_id: str, user: Me) -> SOPOut:
    with db.session() as ses:
        return _sop_out(_get_sop(ses, sop_id, user))


@router.post("", response_model=UploadOut, status_code=202)
async def upload_sop(
    user: Me,
    file: UploadFile = File(...),
    sop_id: str | None = Form(None, description="Existing SOP id to add a new revision (re-upload)"),
    name: str | None = Form(None), plant: str | None = Form(None), line: str | None = Form(None),
    station: str | None = Form(None),
) -> UploadOut:
    data = await read_upload(file)
    fname = file.filename or "upload"
    with db.session() as ses:
        if sop_id:
            sop = _get_sop(ses, sop_id, user)
        else:
            sop = db.SOP(name=name or fname.rsplit(".", 1)[0], plant=plant, line=line, station=station,
                         owner_id=user.id if user else None)
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


@router.get("/{sop_id}/revisions/{number}/document", response_model=SOPDocument)
def get_document(sop_id: str, number: int, user: Me) -> SOPDocument:
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number, user)
        if not r.document:
            raise HTTPException(409, f"revision is {r.status}; no document yet")
        return SOPDocument.model_validate(r.document)


@router.put("/{sop_id}/revisions/{number}/document", response_model=SOPDocument)
def put_document(sop_id: str, number: int, doc: SOPDocument, user: Me) -> SOPDocument:
    """Human-reviewed extraction replaces the machine one; scoring uses this version."""
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number, user)
        if r.status in ("ingesting", "failed"):
            raise HTTPException(409, f"revision is {r.status}")
        for i, we in enumerate(sorted(doc.work_elements, key=lambda w: w.seq), start=1):
            we.seq = i
        r.document = doc.model_dump(mode="json", by_alias=True)
        r.status = "reviewed"
        ses.commit()
        return doc


@router.post("/{sop_id}/revisions/{number}/evidence", response_model=EvidenceItem, status_code=201)
async def add_evidence(sop_id: str, number: int, user: Me, file: UploadFile = File(...),
                       level: str = Form(..., pattern="^L[23]$"), kind: str = Form("document"),
                       title: str | None = Form(None)) -> EvidenceItem:
    data = await read_upload(file)
    with db.session() as ses:
        rev_id = _get_revision(ses, sop_id, number, user).id
    item = await services.evidence_from_bytes(file.filename or "evidence", data, level, kind, title)
    with db.session() as ses:
        ses.add(db.Evidence(revision_id=rev_id, item=item.model_dump(mode="json")))
        ses.commit()
    return item


@router.delete("/{sop_id}/revisions/{number}/evidence/{evidence_id}", status_code=204)
def delete_evidence(sop_id: str, number: int, evidence_id: str, user: Me) -> None:
    with db.session() as ses:
        rev = _get_revision(ses, sop_id, number, user)
        for e in rev.evidence:
            if e.item.get("id") == evidence_id:
                ses.delete(e)
        ses.commit()


@router.post("/{sop_id}/revisions/{number}/assess", response_model=AssessOut, status_code=202)
async def assess_revision(sop_id: str, number: int, user: Me) -> AssessOut:
    with db.session() as ses:
        r = _get_revision(ses, sop_id, number, user)
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
