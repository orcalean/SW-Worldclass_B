"""Shared by the v1 route modules: job response models and upload validation."""
from __future__ import annotations

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.ingestion.loaders import SUPPORTED
from app.storage import db

MAX_UPLOAD = 50 * 1024 * 1024


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


async def read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file exceeds {MAX_UPLOAD // 1024 // 1024} MB")
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in SUPPORTED:
        raise HTTPException(415, f"unsupported type {suffix}; supported: {sorted(SUPPORTED)}")
    return data


def job_out(j: db.Job) -> JobOut:
    return JobOut(id=j.id, kind=j.kind, status=j.status, stage=j.stage, error=j.error,
                  result_type=j.result_type, result_id=j.result_id, result=j.result)
