# 2026-10-24 · First real Claude run: extraction fixes

## What was done
- Owner hit `ValueError: Streaming is required...` on PDF upload (Docker). [app/llm/client.py](../../../app/llm/client.py) now uses `beta.messages.stream(...)` + `get_final_message()`; schema-invalid/truncated output raises `LLMError`.
- Next real error: "compiled grammar is too large". [app/ingestion/structurer.py](../../../app/ingestion/structurer.py) `ExtractionBatch` flattened (all required, no nullables, plain-string enums) + normalizers; [app/ingestion/offline.py](../../../app/ingestion/offline.py) adapted. Evaluation schema was probed and is accepted unchanged.
- `ExtractionFailed` raised when every page batch fails (job fails instead of an empty document). Test added (29 tests).
- Real run on synthetic 1-page PDF: extraction correct (5 elements, key point, specs incl. "specified" force), $0.015; evaluation 12 calls, $0.14, L1 17.2, gate blocked (Q01-3-01, 7-01, 7-04).

## Decisions
- Owner: keep scope simple for now: best case = digital PDF upload; photo handling improvements later.

## Not done / next steps
- Owner decisions: conditional checks marked `gap` when SOP is silent; cross-subcategory root de-dup (see STATUS Todo).
- Run on real customer PDFs.

## How to verify
```bash
uv run pytest     # 29 passed
# real (costs ~$0.16): upload a PDF via the UI with SWC_LLM_PROVIDER=anthropic
```
