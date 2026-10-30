"""v1 API: combines every v1 router into one `router` that main.py includes.

  auth.py         /v1/auth/*  login, logout, me       (public)
  health.py       /v1/health                           (everything below needs require_auth)
  rubrics.py      /v1/rubrics[/{id}]
  jobs.py         /v1/ingest, /v1/evaluate, /v1/jobs/{id}   black-box, stateless
  sops.py         /v1/sops/...                          workspace: revisions, review, evidence, assess
  assessments.py  /v1/assessments/{id}, /v1/blobs/...
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import assessments, auth, health, jobs, rubrics, sops
from app.auth import require_auth

# Session cookie (UI users) or X-API-Key (service callers); see app/auth and ADR 0009.
protected = APIRouter(prefix="/v1", dependencies=[Depends(require_auth)])
for module in (health, rubrics, jobs, sops, assessments):
    protected.include_router(module.router)

router = APIRouter()
router.include_router(auth.router)
router.include_router(protected)
