from datetime import datetime, timezone
from typing import Any, List, Optional

from ..models.span import Span
from ..core.cost_calculator import calculate_cost
from ..core.payload import max_payload_chars, truncate_payload


def _append_capped(parts: List[str], piece: str) -> None:
    """Stop buffering stream chunks once we already hold max_payload_chars."""
    limit = max_payload_chars()
    if limit < 0:
        parts.append(piece)
        return
    if limit == 0:
        return
    held = sum(len(p) for p in parts)
    if held >= limit:
        return
    parts.append(piece[: limit - held])


def _finalize(span: Span, trace: Any, model: str, tokens_in: int, tokens_out: int,
              cached: int, content_parts: List[str]) -> None:
    span.finished_at = datetime.now(timezone.utc)
    span.tokens_in = int(tokens_in or 0)
    span.tokens_out = int(tokens_out or 0)
    span.tokens_in_cached = int(cached or 0)
    span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached)
    if content_parts:
        span.output = truncate_payload("".join(content_parts))
    trace.spans.append(span)


def _openai_chunk(chunk, content_parts: List[str], usage_holder: dict) -> None:
    u = getattr(chunk, "usage", None)
    if u is not None:
        usage_holder["input"] = getattr(u, "prompt_tokens", 0) or 0
        usage_holder["output"] = getattr(u, "completion_tokens", 0) or 0
        details = getattr(u, "prompt_tokens_details", None)
        usage_holder["cached"] = getattr(details, "cached_tokens", 0) or 0
    try:
        delta = chunk.choices[0].delta
        piece = getattr(delta, "content", None)
        if piece:
            _append_capped(content_parts, piece)
    except (IndexError, AttributeError, TypeError):
        pass


def stream_openai(raw, span, trace, model):
    parts: List[str] = []
    usage = {"input": 0, "output": 0, "cached": 0}
    try:
        for chunk in raw:
            _openai_chunk(chunk, parts, usage)
            yield chunk
    finally:
        _finalize(span, trace, model, usage["input"], usage["output"], usage["cached"], parts)


async def astream_openai(raw, span, trace, model):
    parts: List[str] = []
    usage = {"input": 0, "output": 0, "cached": 0}
    try:
        async for chunk in raw:
            _openai_chunk(chunk, parts, usage)
            yield chunk
    finally:
        _finalize(span, trace, model, usage["input"], usage["output"], usage["cached"], parts)


def _anthropic_event(event, parts: List[str], usage_holder: dict) -> None:
    etype = getattr(event, "type", None)
    if etype == "message_start":
        msg_usage = getattr(getattr(event, "message", None), "usage", None)
        if msg_usage is not None:
            usage_holder["input"] = getattr(msg_usage, "input_tokens", 0) or 0
            usage_holder["cached"] = getattr(msg_usage, "cache_read_input_tokens", 0) or 0
    elif etype == "message_delta":
        delta_usage = getattr(event, "usage", None)
        if delta_usage is not None:
            usage_holder["output"] = getattr(delta_usage, "output_tokens", 0) or 0
    elif etype == "content_block_delta":
        piece = getattr(getattr(event, "delta", None), "text", None)
        if piece:
            _append_capped(parts, piece)


def stream_anthropic(raw, span, trace, model):
    parts: List[str] = []
    usage = {"input": 0, "output": 0, "cached": 0}
    try:
        for event in raw:
            _anthropic_event(event, parts, usage)
            yield event
    finally:
        _finalize(span, trace, model, usage["input"], usage["output"], usage["cached"], parts)


async def astream_anthropic(raw, span, trace, model):
    parts: List[str] = []
    usage = {"input": 0, "output": 0, "cached": 0}
    try:
        async for event in raw:
            _anthropic_event(event, parts, usage)
            yield event
    finally:
        _finalize(span, trace, model, usage["input"], usage["output"], usage["cached"], parts)
