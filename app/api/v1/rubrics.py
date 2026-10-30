"""Rubric catalogue.

  GET /v1/rubrics            dimensions, cores and policy
  GET /v1/rubrics/{core_id}  one assessed core with its checks
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.rubric.registry import load_catalogue

router = APIRouter(prefix="/rubrics", tags=["rubrics"])


@router.get("")
def rubrics() -> dict[str, Any]:
    cat = load_catalogue()
    return {
        "policy": cat.policy.model_dump(),
        "dimensions": [{"key": d.key, "name": d.name, "cores": [
            {"id": f"{d.key}.core{c.number}", "number": c.number, "name": c.name, "assessed": c.core is not None,
             "version": c.core.version if c.core else None,
             "checks": len(c.core.checks()) if c.core else 0} for c in d.cores]} for d in cat.dimensions],
    }


@router.get("/{core_id}")
def rubric(core_id: str) -> dict[str, Any]:
    for core in load_catalogue().assessed_cores():
        if core.id == core_id:
            return core.model_dump()
    raise HTTPException(404, "rubric not found or not yet assessed")
