"""Module A: LoadedDocument -> SOPDocument. Fidelity only; no judgement of quality.

Pages are sent in batches (rendered image + text layer + embedded images by id). The model returns a
flat, schema-validated ExtractionBatch; batches are merged in code (continuations joined, seq renumbered).
A coverage check compares the text layer with extracted text and warns on likely misses.
"""
from __future__ import annotations

import asyncio
import base64
import re

from pydantic import BaseModel, Field

from app.contracts.sop import (
    Asset, LimitDirection, Provenance, SOPDocument, SOPGlobal, SOPMeta, SourceInfo, Spec, Step, WorkElement,
)
from app.ingestion.loaders import LoadedDocument, Page
from app.llm.client import LLM, CallUsage, LLMError, Request

EXTRACT_PROMPT_VERSION = "extract-1.0"

SYSTEM = """You convert Standard Work Instructions / SOPs / JES / process sheets into structured data.
Documents vary widely: tables, multi-column job element sheets, photo callouts, scanned pages, spreadsheets.

Rules:
- Transcribe; never improve, correct, complete or judge the instruction. Copy step text verbatim.
- A work element is one numbered/major step of the job (a row of a JES table, a numbered step, a slide step).
  Put its sub-instructions, key points and reasons in steps with the right kind
  (step | key_point | reason | check | warning | note).
- specs: every value-bearing requirement (torque, force, time, temperature, gap, count, ...) as written.
  If the SOP says "per spec"/"specified" without a value, record value exactly as written, unit null.
  direction: min/max/range/nominal/exact as stated, else unknown.
- quality_marks: critical/special characteristic symbols, safety icons or flags shown next to the element.
- Images: for every image id listed, give a factual description of what it shows and any text visible in it
  (callouts, labels, arrows' captions), and attach the image id to the work element it illustrates.
- page: the page number where each item appears.
- If the first work element on these pages continues one from the previous page, set continues_previous.
- warnings: anything you could not read or are unsure about (illegible, cut off, ambiguous order).
"""


# LLM output schema. Kept deliberately flat: every field required, no nullable unions, no numeric
# constraints, enums as plain strings. Structured outputs compile the schema into a grammar and
# reject large ones ("compiled grammar is too large"). Empty string = absent; values are
# normalized in code (_clean / _kind / _direction) when building the SOPDocument.
STEP_KINDS = {"step", "key_point", "reason", "check", "warning", "note"}
DIRECTIONS = {"min", "max", "range", "nominal", "exact", "unknown"}


class ExtractionFailed(RuntimeError):
    pass


class XStep(BaseModel):
    text: str
    kind: str = Field(description="step | key_point | reason | check | warning | note")
    page: int


class XSpec(BaseModel):
    characteristic: str
    value: str
    unit: str
    tolerance: str
    direction: str = Field(description="min | max | range | nominal | exact | unknown")
    reference: str
    page: int


class XWorkElement(BaseModel):
    title: str
    continues_previous: bool
    steps: list[XStep]
    specs: list[XSpec]
    quality_marks: list[str]
    references: list[str]
    image_ids: list[str]
    page: int
    confidence: float = Field(description="0-1 extraction confidence")


class XImage(BaseModel):
    id: str
    description: str
    text_in_image: str


class XMeta(BaseModel):
    title: str
    swi_id: str
    revision: str
    effective_date: str
    owner: str
    plant: str
    line: str
    station: str
    language: str
    products: list[str]


class XGeneral(BaseModel):
    ppe: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    revision_history: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExtractionBatch(BaseModel):
    meta: XMeta
    work_elements: list[XWorkElement]
    images: list[XImage]
    general: XGeneral
    warnings: list[str]


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v if v and v.lower() not in ("null", "none", "n/a", "-") else None


def _kind(v: str) -> str:
    v = (v or "").strip().lower().replace(" ", "_")
    return v if v in STEP_KINDS else "step"


def _direction(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in DIRECTIONS else "unknown"


def empty_batch(warnings: list[str]) -> ExtractionBatch:
    return ExtractionBatch(meta=XMeta(title="", swi_id="", revision="", effective_date="", owner="", plant="",
                                      line="", station="", language="", products=[]),
                           work_elements=[], images=[], general=XGeneral(), warnings=warnings)


def img_block(png: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(png).decode()}}


def _batch_content(pages: list[Page]) -> list[dict]:
    blocks: list[dict] = []
    for p in pages:
        blocks.append({"type": "text", "text": f"=== PAGE {p.number} ==="})
        if p.render_png:
            blocks.append(img_block(p.render_png))
        if p.text:
            blocks.append({"type": "text", "text": f"<text_layer page=\"{p.number}\">\n{p.text}\n</text_layer>"})
        for im in p.images:
            blocks.append({"type": "text", "text": f"Image id {im.id} (page {p.number}, bbox {im.bbox}):"})
            blocks.append(img_block(im.png))
    blocks.append({"type": "text", "text": "Extract pages "
                   f"{pages[0].number}-{pages[-1].number} into the schema."})
    return blocks


def _merge(batches: list[ExtractionBatch]) -> tuple[SOPMeta, list[XWorkElement], dict[str, XImage], XGeneral, list[str]]:
    meta = SOPMeta()
    wes: list[XWorkElement] = []
    images: dict[str, XImage] = {}
    general = XGeneral()
    warnings: list[str] = []
    for b in batches:
        for k, v in b.meta.model_dump().items():
            if k == "products":
                meta.products += [x for x in (_clean(i) for i in v) if x and x not in meta.products]
            elif (v := _clean(v)) and not getattr(meta, k):
                setattr(meta, k, v)
        for we in b.work_elements:
            if we.continues_previous and wes:
                prev = wes[-1]
                prev.steps += we.steps
                prev.specs += we.specs
                prev.quality_marks += [q for q in we.quality_marks if q not in prev.quality_marks]
                prev.references += [r for r in we.references if r not in prev.references]
                prev.image_ids += we.image_ids
                prev.confidence = min(prev.confidence, we.confidence)
            else:
                wes.append(we.model_copy(deep=True))
        for im in b.images:
            images.setdefault(im.id, im)
        for f in XGeneral.model_fields:
            cur = getattr(general, f)
            cur += [x for x in getattr(b.general, f) if x not in cur]
        warnings += b.warnings
    return meta, wes, images, general, warnings


_WORD = re.compile(r"[a-z0-9]{3,}")


def coverage_warnings(pages: list[Page], doc: SOPDocument, threshold: float = 0.6) -> list[str]:
    """Share of each page's text-layer words that made it into the structured document."""
    extracted = set(_WORD.findall(doc.all_text().lower()))
    out = []
    for p in pages:
        words = _WORD.findall(p.text.lower())
        if len(words) < 15:
            continue
        cov = sum(w in extracted for w in words) / len(words)
        if cov < threshold:
            out.append(f"page {p.number}: only {cov:.0%} of the page text was captured - review extraction")
    return out


async def structure(loaded: LoadedDocument, llm: LLM, model: str, usage: CallUsage,
                    effort: str = "low", pages_per_call: int = 4) -> SOPDocument:
    groups = [loaded.pages[i:i + pages_per_call] for i in range(0, len(loaded.pages), pages_per_call)]

    async def run(g: list[Page]) -> ExtractionBatch:
        req = Request(task=f"extract.p{g[0].number}-{g[-1].number}", model=model, system=SYSTEM, shared=[],
                      prompt=_batch_content(g), schema=ExtractionBatch, effort=effort, max_tokens=32000,
                      meta={"pages": g, "filename": loaded.filename})
        try:
            return await llm.structured(req, usage)  # type: ignore[return-value]
        except LLMError as e:
            failed.append(f"pages {g[0].number}-{g[-1].number}: {e}")
            return empty_batch([f"pages {g[0].number}-{g[-1].number}: extraction failed ({e})"])

    failed: list[str] = []
    batches = list(await asyncio.gather(*(run(g) for g in groups)))
    if len(failed) == len(groups):
        # Nothing was extracted: fail the job loudly instead of returning an empty document.
        raise ExtractionFailed("extraction failed for every page batch: " + "; ".join(failed))
    meta, xwes, ximages, general, warnings = _merge(batches)

    page_images = {im.id: (p.number, im) for p in loaded.pages for im in p.images}
    assets = []
    for iid, (page_no, im) in page_images.items():
        x = ximages.get(iid)
        assets.append(Asset(id=iid, kind="image", uri=f"blob://{loaded.sha256}/{iid}.png", page=page_no,
                            bbox=im.bbox, description=_clean(x.description) if x else None,
                            text_in_image=_clean(x.text_in_image) if x else None))
    for p in loaded.pages:
        if p.render_png:
            assets.append(Asset(id=f"page-{p.number}", kind="page_render",
                                uri=f"blob://{loaded.sha256}/page-{p.number}.png", page=p.number))

    work_elements = []
    for i, x in enumerate(xwes, start=1):
        conf = min(max(x.confidence, 0.0), 1.0)
        page = x.page or None
        prov = Provenance(page=page, confidence=conf)
        work_elements.append(WorkElement(
            id=f"we-{i}", seq=i, title=x.title.strip(),
            steps=[Step(text=s.text, kind=_kind(s.kind), provenance=Provenance(page=s.page or page, confidence=conf))
                   for s in x.steps if s.text.strip()],
            specs=[Spec(characteristic=s.characteristic, value=_clean(s.value), unit=_clean(s.unit),
                        tolerance=_clean(s.tolerance), direction=LimitDirection(_direction(s.direction)),
                        reference=_clean(s.reference),
                        provenance=Provenance(page=s.page or page, confidence=conf)) for s in x.specs],
            quality_marks=x.quality_marks, references=x.references,
            asset_ids=[a for a in dict.fromkeys(x.image_ids) if a in page_images], provenance=prov,
        ))

    doc = SOPDocument(
        source=SourceInfo(filename=loaded.filename, format=loaded.format, sha256=loaded.sha256,
                          pages=len(loaded.pages)),
        meta=meta, work_elements=work_elements, assets=assets,
        global_=SOPGlobal(**general.model_dump()),
    )
    if not work_elements:
        warnings.append("no work elements were extracted - check the file or use manual entry")
    low = [w.id for w in work_elements if w.provenance.confidence < 0.6]
    if low:
        warnings.append(f"low extraction confidence on {', '.join(low)} - review before scoring")
    doc.extraction_warnings = loaded.warnings + warnings + coverage_warnings(loaded.pages, doc)
    return doc
