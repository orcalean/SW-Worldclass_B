"""Results and stored files.

  GET /v1/assessments/{id}    EvaluationResult
  GET /v1/blobs/{sha}/{name}  page renders / images referenced by documents and evidence

An assessment of a workspace revision follows its SOP's access (ADR 0010); stateless /v1/evaluate results have no
revision and stay readable by id.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.v1.sops import Me, visible
from app.contracts.evaluation import EvaluationResult
from app.storage import db

router = APIRouter(tags=["assessments"])


@router.get("/assessments/{assessment_id}", response_model=EvaluationResult)
def get_assessment(assessment_id: str, user: Me) -> EvaluationResult:
    with db.session() as ses:
        a = ses.get(db.Assessment, assessment_id)
        if not a or (a.revision is not None and not visible(user, a.revision.sop)):
            raise HTTPException(404, "assessment not found")
        return EvaluationResult.model_validate(a.result)


@router.get("/blobs/{sha}/{name}")
def blob(sha: str, name: str) -> FileResponse:
    p = db.Blobs().path(sha, name)
    if p is None:
        raise HTTPException(404, "not found")
    return FileResponse(p)
