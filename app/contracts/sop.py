"""Canonical SOPDocument: the single contract between ingestion and evaluation.

Any producer (our file ingestion, or the SWP app in Ph2, which stores SOPs as text + images)
can POST this shape to /v1/evaluate. Ingestion never judges; evaluation never parses files.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "sop-document/1.0"


class Provenance(BaseModel):
    page: int | None = Field(None, description="1-based source page, if from a file")
    bbox: list[float] | None = Field(None, description="[x0,y0,x1,y1] in page points")
    confidence: float = Field(1.0, ge=0, le=1, description="Extraction confidence; 1.0 for human/structured input")


class LimitDirection(str, Enum):
    min = "min"
    max = "max"
    range = "range"
    nominal = "nominal"
    exact = "exact"
    unknown = "unknown"


class Spec(BaseModel):
    characteristic: str = Field(..., description="What is controlled, e.g. 'application force'")
    value: str | None = Field(None, description="Value as written, e.g. '25' or 'per spec'")
    unit: str | None = None
    tolerance: str | None = None
    direction: LimitDirection = LimitDirection.unknown
    reference: str | None = Field(None, description="Controlled document reference, if cited")
    provenance: Provenance = Field(default_factory=Provenance)


class Step(BaseModel):
    text: str
    kind: str = Field("step", description="step | key_point | reason | check | warning | note")
    provenance: Provenance = Field(default_factory=Provenance)


class WorkElement(BaseModel):
    id: str = Field(..., description="Stable id within the document, e.g. 'we-4'")
    seq: int
    title: str
    steps: list[Step] = Field(default_factory=list)
    specs: list[Spec] = Field(default_factory=list)
    quality_marks: list[str] = Field(default_factory=list, description="Critical/special symbols or flags shown")
    references: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list, description="Images belonging to this element")
    provenance: Provenance = Field(default_factory=Provenance)


class Asset(BaseModel):
    id: str
    kind: str = Field("image", description="image | page_render | video | drawing")
    uri: str | None = Field(None, description="Blob URI; producers may omit when only describing")
    page: int | None = None
    bbox: list[float] | None = None
    description: str | None = Field(None, description="What the image shows (vision model or human)")
    text_in_image: str | None = Field(None, description="Text visible inside the image, incl. callouts")


class SOPMeta(BaseModel):
    title: str | None = None
    swi_id: str | None = None
    revision: str | None = None
    effective_date: str | None = None
    owner: str | None = None
    plant: str | None = None
    line: str | None = None
    station: str | None = None
    products: list[str] = Field(default_factory=list, description="Models / variants / part families covered")
    language: str | None = None


class SOPGlobal(BaseModel):
    ppe: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    revision_history: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    filename: str | None = None
    format: str = Field("structured", description="pdf | docx | xlsx | pptx | image | structured")
    sha256: str | None = None
    pages: int | None = None


class SOPDocument(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: SourceInfo = Field(default_factory=SourceInfo)
    meta: SOPMeta = Field(default_factory=SOPMeta)
    work_elements: list[WorkElement] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    global_: SOPGlobal = Field(default_factory=SOPGlobal, alias="global")
    extraction_warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def all_text(self) -> str:
        """Flattened text used by the citation verifier."""
        # Header fields are indexed as "field: value" so short values (rev "7") can be quoted unambiguously.
        parts: list[str] = [f"{k}: {v}" for k, v in self.meta.model_dump().items() if isinstance(v, str)]
        parts += self.meta.products
        for we in self.work_elements:
            parts.append(we.title)
            parts += [s.text for s in we.steps]
            for sp in we.specs:
                parts += [x for x in (sp.characteristic, sp.value, sp.unit, sp.tolerance, sp.reference) if x]
            parts += we.quality_marks + we.references
        for a in self.assets:
            parts += [x for x in (a.description, a.text_in_image) if x]
        g = self.global_
        for lst in (g.ppe, g.tools, g.materials, g.references, g.revision_history, g.notes):
            parts += lst
        return "\n".join(parts)
