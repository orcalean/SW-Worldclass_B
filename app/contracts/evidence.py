"""Optional L2 (station) / L3 (governing) evidence attached to an evaluation."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    id: str
    level: str = Field(..., pattern="^L[23]$", description="L2 station evidence | L3 governing/customer evidence")
    kind: str = Field("document", description="photo | video | document | spec | control_plan | pfmea | drawing | other")
    title: str | None = None
    filename: str | None = None
    text: str | None = Field(None, description="Extracted text (documents) or human summary")
    description: str | None = Field(None, description="What a photo/video shows (vision model or human)")
    sha256: str | None = None
