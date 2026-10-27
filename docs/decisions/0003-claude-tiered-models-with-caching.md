# 0003. Claude Sonnet 5.5 / Haiku 5.5, tiered, with prompt caching

- Status: Accepted
- Date: 2026-10-24
- Decided by: owner (chose "Claude, tiered + cached")

## Context
Requirements: cost-effective, highly reliable, checks every rubric point. Vision is needed to read SOP photos, callouts and scans.

## Decision
- Extraction and evaluation: `claude-sonnet-5-5`; cheap tasks (station-photo descriptions): `claude-haiku-5-5`. Configurable via `SWC_*_MODEL` in `.env`.
- One evaluation call per rubric subcategory. System prompt + SOP JSON (+ evidence) form a cached prefix; the first call runs alone to write the cache, the rest run concurrently.
- Structured output via `client.beta.messages.stream(output_format=<Pydantic model>)` → `get_final_message()` (streaming is required for large `max_tokens`); server-side refusal fallback (`fallbacks="default"`) on Sonnet/Opus.
- No `temperature`: the API rejects sampling parameters since 2026-10-21. Repeatability comes from categorical verdicts, the result cache and quote verification.
- All LLM access goes through `app/llm/client.py` (`LLM` protocol).

## Consequences
- Target cost ≈ $0.10–0.40 per SOP for Core 1; every assessment reports its cost (`usage.cost_usd`). Not yet measured with real calls.
- Swapping provider means implementing the `LLM` protocol, not touching modules A/B/C.
