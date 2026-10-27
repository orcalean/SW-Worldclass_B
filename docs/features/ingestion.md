# Ingestion (module A): file → SOPDocument

## Key files
| File | Role |
|---|---|
| `app/ingestion/loaders.py` | `load(filename, bytes)` → `LoadedDocument` with pages (rendered PNG ≤1568 px, text layer, embedded images ≥48 px with bbox) |
| `app/ingestion/structurer.py` | `structure(...)`: batches pages to the vision model, merges batches, builds `SOPDocument`, adds warnings |
| `app/ingestion/offline.py` | regex stand-in for the vision model (text layer only) |
| `app/services.py` `ingest_bytes` | saves blobs, extraction cache |
| `tests/unit/test_ingestion.py` | PDF/DOCX loading, offline end-to-end, cross-page continuation, coverage warning |

## How it works
1. **Load.** PDF via PyMuPDF. Images become one page with no text layer. DOCX/PPTX/XLSX are converted to PDF with LibreOffice when installed (`soffice`); otherwise native python-docx / python-pptx / openpyxl extraction (text + images, no render) with a warning.
2. **Structure.** Pages go in groups of `SWC_PAGES_PER_EXTRACTION_CALL`, each with its page render, text layer and image ids. The model returns `ExtractionBatch` (schema-validated; deliberately flat: all fields required, empty string = absent, enums as plain strings, because structured outputs reject large grammars; `_clean` / `_kind` / `_direction` normalize afterwards): meta, work elements (steps with kind, specs as written, quality marks, image ids, page, confidence, `continues_previous`), image descriptions, general info, warnings. Prompt: `SYSTEM` in `structurer.py`; transcribe, never improve.
3. **Merge.** First non-empty meta wins; a work element flagged `continues_previous` is merged into the previous one; elements are renumbered `we-1..n`; unknown image ids are dropped.
4. **Failure:** if every page batch fails, `structure` raises `ExtractionFailed` and the job fails (no empty document). If only some fail, the rest is kept with a warning.
5. **Warnings** (`SOPDocument.extraction_warnings`): loader warnings (no text layer, no LibreOffice), model warnings, failed batches, no work elements, low-confidence elements (<0.6), and **coverage** (`coverage_warnings`): a page where under 60% of text-layer words appear in the extracted document.
6. **Human review** (UI) can correct everything; `PUT .../document` stores the reviewed version and scoring uses it.

## Rules for changing it
- Ingestion must not judge or "fix" the SOP. Quality judgements belong in evaluation.
- Changing the prompt or `ExtractionBatch`: bump `EXTRACT_PROMPT_VERSION` (invalidates the extraction cache).
- Changing `SOPDocument`: it's a public contract; bump `SCHEMA_VERSION`, run `npm run gen:api`, update `docs/design/backend-design.md`.
- Keep the offline handler compatible so `tests/unit/test_ingestion.py` and the API tests keep passing.
