"""GET /v1/health: liveness + which LLM provider and models are configured."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import services
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    p = services.providers(s)
    return {"status": "ok", "llm_provider": s.llm_provider,
            "models": {"extraction": p.extraction_model, "evaluation": p.evaluation_model}}
