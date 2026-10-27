"""Offline heuristic stand-in for the extraction LLM (demo / tests without an API key).

Reads only the text layer: numbered lines become work elements, value+unit patterns become specs.
It cannot read images or scans; real ingestion needs the vision model.
"""
from __future__ import annotations

import re

from app.ingestion.structurer import ExtractionBatch, XGeneral, XImage, XMeta, XSpec, XStep, XWorkElement
from app.llm.client import Request

STEP = re.compile(r"^\s*(?:step\s*)?(\d{1,2})\s*[\.\):-]\s+(.+)$", re.I)
META = {
    "revision": re.compile(r"\brev(?:ision)?\.?\s*[:#]?\s*([A-Z0-9][\w.-]*)", re.I),
    "swi_id": re.compile(r"\b(?:swi|sop|doc(?:ument)?)\s*(?:id|no\.?|number)?\s*[:#]\s*([\w-]+)", re.I),
    "effective_date": re.compile(r"\beffective(?: date)?\s*[:#]?\s*([\d/.-]{8,10})", re.I),
    "station": re.compile(r"\bstation\s*[:#]\s*([\w-]+)", re.I),
    "owner": re.compile(r"\bowner\s*[:#]\s*(.+)$", re.I | re.M),
}
VALUE = re.compile(r"(\d+(?:\.\d+)?)\s*(N·m|Nm|N|s|sec|seconds|mm|°C|C|psi|kPa|bar|%)\b(?:\s*(?:±|\+/-)\s*(\d+(?:\.\d+)?))?")
VAGUE_SPEC = re.compile(r"\b(specified|per spec(?:ification)?)\s+(\w+)", re.I)
DIRECTION = re.compile(r"\b(min(?:imum)?|max(?:imum)?|at least|not to exceed)\b", re.I)


def _specs(text: str, page: int) -> list[XSpec]:
    out = []
    d = DIRECTION.search(text)
    direction = "unknown" if not d else ("min" if d.group(1).lower().startswith(("min", "at")) else "max")
    for m in VALUE.finditer(text):
        out.append(XSpec(characteristic=text[:40], value=m.group(1), unit=m.group(2), tolerance=m.group(3) or "",
                         direction="range" if m.group(3) else direction, reference="", page=page))
    for m in VAGUE_SPEC.finditer(text):
        out.append(XSpec(characteristic=m.group(2), value=m.group(0), unit="", tolerance="", direction="unknown",
                         reference="", page=page))
    return out


def handler(req: Request) -> ExtractionBatch:
    pages = req.meta["pages"]
    meta = XMeta(title="", swi_id="", revision="", effective_date="", owner="", plant="", line="", station="",
                 language="", products=[])
    wes: list[XWorkElement] = []
    images: list[XImage] = []
    for p in pages:
        lines = [ln.strip() for ln in p.text.splitlines() if ln.strip()]
        if p.number == 1 and lines:
            meta.title = lines[0][:120]
        for key, rx in META.items():
            if not getattr(meta, key) and (m := rx.search(p.text)):
                setattr(meta, key, m.group(1).strip())
        first_on_page = None
        for ln in lines:
            if m := STEP.match(ln):
                we = _we(m.group(2)[:80], p.number, steps=[XStep(text=m.group(2), kind="step", page=p.number)],
                         specs=_specs(m.group(2), p.number))
                wes.append(we)
                first_on_page = first_on_page or we
            elif (wes and wes[-1].page == p.number) or (p.number > 1 and not first_on_page):
                if not wes or wes[-1].page != p.number:
                    # text at the top of a page before any numbered step continues the previous page's element
                    wes.append(_we("(continued)", p.number, continues_previous=True))
                kind = "key_point" if ln.lower().startswith(("key point", "kp:", "note")) else "step"
                wes[-1].steps.append(XStep(text=ln, kind=kind, page=p.number))
                wes[-1].specs += _specs(ln, p.number)
        for im in p.images:
            images.append(XImage(id=im.id, description="(image not described offline)", text_in_image=""))
            if first_on_page:
                first_on_page.image_ids.append(im.id)
    return ExtractionBatch(meta=meta, work_elements=wes, images=images, general=XGeneral(),
                           warnings=["offline extraction: text layer only, images not interpreted"])


def _we(title: str, page: int, steps=None, specs=None, continues_previous: bool = False) -> XWorkElement:
    return XWorkElement(title=title, continues_previous=continues_previous, steps=steps or [], specs=specs or [],
                        quality_marks=[], references=[], image_ids=[], page=page, confidence=0.5)
