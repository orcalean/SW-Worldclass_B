"""Orchestration used by the API: providers, caching, persistence. Modules A/B/C stay storage-agnostic."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.contracts.evaluation import EvaluationResult
from app.contracts.evidence import EvidenceItem
from app.contracts.sop import SOPDocument
from app.evaluation import offline as eval_offline
from app.evaluation.engine import cache_key, evaluate
from app.ingestion import offline as ingest_offline
from app.ingestion.loaders import load
from app.ingestion.structurer import EXTRACT_PROMPT_VERSION, img_block, structure
from app.llm.client import LLM, AnthropicLLM, CallUsage, Request, ScriptedLLM
from app.rubric.registry import load_catalogue
from app.storage import db


class PhotoDescription(BaseModel):
    description: str


@dataclass
class Providers:
    extraction: LLM
    evaluation: LLM
    extraction_model: str
    evaluation_model: str


def providers(s: Settings | None = None) -> Providers:
    s = s or get_settings()
    if s.llm_provider == "offline":
        return Providers(ScriptedLLM(ingest_offline.handler, "offline"), ScriptedLLM(eval_offline.handler, "offline"),
                         "offline", "offline")
    llm = AnthropicLLM(refusal_fallback=s.refusal_fallback, max_concurrency=s.max_concurrency,
                       api_key=s.anthropic_api_key)
    return Providers(llm, llm, s.extraction_model, s.evaluation_model)


async def ingest_bytes(filename: str, data: bytes, p: Providers | None = None) -> tuple[SOPDocument, float]:
    """File -> SOPDocument. Cached by file hash + prompt version + model; page renders/images saved as blobs."""
    s = get_settings()
    p = p or providers(s)
    loaded = load(filename, data)
    blobs = db.Blobs()
    for page in loaded.pages:
        if page.render_png:
            blobs.put(loaded.sha256, f"page-{page.number}.png", page.render_png)
        for im in page.images:
            blobs.put(loaded.sha256, f"{im.id}.png", im.png)
    blobs.put(loaded.sha256, f"source{_suffix(filename)}", data)

    key = hashlib.sha256(f"{loaded.sha256}|{EXTRACT_PROMPT_VERSION}|{p.extraction.name}|{p.extraction_model}"
                         .encode()).hexdigest()
    with db.session() as ses:
        hit = ses.get(db.ExtractionCache, key)
        if hit:
            doc = SOPDocument.model_validate(hit.document)
            doc.source.filename = filename
            return doc, 0.0
    usage = CallUsage()
    doc = await structure(loaded, p.extraction, p.extraction_model, usage, s.extraction_effort,
                          s.pages_per_extraction_call)
    with db.session() as ses:
        ses.merge(db.ExtractionCache(key=key, document=doc.model_dump(mode="json", by_alias=True),
                                     cost_usd=usage.cost_usd))
        ses.commit()
    return doc, usage.cost_usd


async def evidence_from_bytes(filename: str, data: bytes, level: str, kind: str, title: str | None,
                              p: Providers | None = None) -> EvidenceItem:
    """Documents contribute their text layer; photos get a vision description (or a placeholder offline)."""
    p = p or providers()
    loaded = load(filename, data)
    db.Blobs().put(loaded.sha256, f"evidence{_suffix(filename)}", data)
    text = "\n\n".join(pg.text for pg in loaded.pages if pg.text) or None
    description = None
    if loaded.format == "image":
        if p.evaluation.name == "offline":
            description = f"Photo '{filename}' (not described offline)"
        else:
            out = await p.evaluation.structured(Request(
                task="evidence.describe", model=get_settings().cheap_model,
                system="Describe factually what this manufacturing station photo shows: product, features, "
                       "labels, displays, fixtures, visual aids, lighting and any visible text. No judgement.",
                shared=[], prompt=[img_block(loaded.pages[0].render_png), {"type": "text", "text": f"Photo: {filename}"}],
                schema=PhotoDescription, effort="low", max_tokens=2000), CallUsage())
            description = out.description  # type: ignore[attr-defined]
    return EvidenceItem(id=f"ev-{loaded.sha256[:10]}", level=level, kind=kind, title=title or filename,
                        filename=filename, text=text, description=description, sha256=loaded.sha256)


async def assess(doc: SOPDocument, evidence: list[EvidenceItem], p: Providers | None = None,
                 revision_id: str | None = None) -> tuple[str, EvaluationResult]:
    """Evaluate with result caching: identical inputs return the stored result (score never drifts)."""
    s = get_settings()
    p = p or providers(s)
    cat = load_catalogue()
    key = cache_key(doc, evidence, cat, p.evaluation.name, p.evaluation_model)
    with db.session() as ses:
        hit = ses.query(db.Assessment).filter_by(cache_key=key).order_by(db.Assessment.created_at.desc()).first()
        if hit:
            res = EvaluationResult.model_validate(hit.result)
            res.usage.cached_result = True
            res.usage.cost_usd = 0.0
            if revision_id and hit.revision_id != revision_id:
                a = db.Assessment(revision_id=revision_id, cache_key=key, score=res.overall.score,
                                  status=res.overall.status, result=res.model_dump(mode="json"))
                ses.add(a)
                ses.commit()
                return a.id, res
            return hit.id, res
    res = await evaluate(doc, evidence, cat, p.evaluation, p.evaluation_model, s.evaluation_effort)
    with db.session() as ses:
        a = db.Assessment(revision_id=revision_id, cache_key=key, score=res.overall.score,
                          status=res.overall.status, result=res.model_dump(mode="json"))
        ses.add(a)
        ses.commit()
        return a.id, res


def _suffix(name: str) -> str:
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
