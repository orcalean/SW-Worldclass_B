"""Thin LLM boundary. Everything above this file speaks Pydantic in / Pydantic out.

- AnthropicLLM: client.beta.messages.stream with Pydantic output_format (schema-validated JSON; streamed because
  large max_tokens requires it),
  a cache breakpoint at the end of the shared prefix, and server-side refusal fallback.
  No temperature: sampling params are rejected by the API; determinism comes from categorical
  outputs + result caching + citation verification, not sampling.
- ScriptedLLM: deterministic handler for tests and the offline demo provider.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# USD per 1M tokens: (input, output, cache_read, cache_write_5m)
PRICING = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}


@dataclass
class CallUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    by_task: dict[str, float] = field(default_factory=dict)

    def add(self, task: str, model: str, inp: int, out: int, cr: int, cw: int) -> None:
        p = PRICING.get(model, PRICING["claude-sonnet-5-5"])
        cost = (inp * p[0] + out * p[1] + cr * p[2] + cw * p[3]) / 1_000_000
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.cache_read_tokens += cr
        self.cache_write_tokens += cw
        self.cost_usd += cost
        self.by_task[task] = self.by_task.get(task, 0.0) + cost


@dataclass
class Request:
    task: str                     # e.g. "extract.pages", "evaluate.1.3"
    model: str
    system: str                   # stable instructions (cached)
    shared: list[dict]            # stable content blocks shared across calls (cached), e.g. the SOP JSON
    prompt: list[dict]            # varying suffix for this call
    schema: type[BaseModel]
    effort: str = "medium"
    max_tokens: int = 16000
    meta: dict[str, Any] = field(default_factory=dict)  # passed through to scripted handlers


class LLM(Protocol):
    name: str

    async def structured(self, req: Request, usage: CallUsage) -> BaseModel: ...


class LLMError(RuntimeError):
    pass


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, refusal_fallback: bool = True, max_concurrency: int = 6, api_key: str = ""):
        import anthropic

        self._anthropic = anthropic
        # Empty key -> SDK resolves credentials itself (env var or `ant auth login` profile).
        self.client = anthropic.AsyncAnthropic(api_key=api_key or None, max_retries=4)
        self.refusal_fallback = refusal_fallback
        self.sem = asyncio.Semaphore(max_concurrency)

    async def structured(self, req: Request, usage: CallUsage) -> BaseModel:
        shared = [dict(b) for b in req.shared]
        if shared:
            shared[-1] = {**shared[-1], "cache_control": {"type": "ephemeral"}}
        kwargs: dict[str, Any] = dict(
            model=req.model,
            max_tokens=req.max_tokens,
            system=[{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": shared + req.prompt}],
            output_format=req.schema,
            output_config={"effort": req.effort},
        )
        if self.refusal_fallback and req.model in ("claude-sonnet-5-5", "claude-opus-5-5"):
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        async with self.sem:
            try:
                # Streaming is required by the SDK for large max_tokens (long-running requests);
                # get_final_message() returns the same parsed message as messages.parse().
                async with self.client.beta.messages.stream(**kwargs) as stream:
                    resp = await stream.get_final_message()
            except self._anthropic.BadRequestError as e:
                raise LLMError(f"{req.task}: bad request: {e.message}") from e
            except self._anthropic.APIStatusError as e:
                raise LLMError(f"{req.task}: API error {e.status_code}: {e.message}") from e
            except self._anthropic.APIConnectionError as e:
                raise LLMError(f"{req.task}: connection error") from e
            except ValidationError as e:
                # The SDK parses at end of stream; truncated (max_tokens) or malformed JSON lands here.
                raise LLMError(f"{req.task}: output was not valid for the schema (truncated?): {e.errors()[0]['msg']}") from e
        u = resp.usage
        usage.add(req.task, req.model, u.input_tokens, u.output_tokens,
                  u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
        if resp.stop_reason == "refusal":
            raise LLMError(f"{req.task}: model declined ({getattr(resp.stop_details, 'category', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"{req.task}: output truncated at max_tokens={req.max_tokens}")
        parsed = resp.parsed_output
        if parsed is None:
            raise LLMError(f"{req.task}: no parsed output (request {resp._request_id})")
        return parsed


class ScriptedLLM:
    """Calls handler(req) -> schema instance. Zero cost; used by tests and the offline provider."""

    def __init__(self, handler: Callable[[Request], BaseModel], name: str = "scripted"):
        self.handler = handler
        self.name = name

    async def structured(self, req: Request, usage: CallUsage) -> BaseModel:
        usage.add(req.task, req.model, 0, 0, 0, 0)
        out = self.handler(req)
        return req.schema.model_validate(out.model_dump() if isinstance(out, BaseModel) else out)
