"""Results and stored files.

  GET /v1/assessments/{id}    EvaluationResult
  GET /v1/blobs/{sha}/{name}  page renders / images referenced by documents and evidence
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.contracts.evaluation import EvaluationResult
from app.storage import db

router = APIRouter(tags=["assessments"])


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
