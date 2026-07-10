from __future__ import annotations

import logging
import os
from typing import Iterable, List, Literal, Optional, Set

from ..models.span import Span, SpanType

_logger = logging.getLogger("tracecast")

SpanFilterMode = Literal["all", "flow", "llm_tool"]

DEFAULT_SPAN_FILTER: SpanFilterMode = "all"

_NOISE_BARE_NAMES: Set[str] = {
    "RunnableSequence",
    "RunnableParallel",
    "RunnableLambda",
    "RunnableEach",
    "RunnableAssign",
    "RunnablePassthrough",
    "Prompt",
    "ChatPromptTemplate",
    "call_model",
    "should_continue",
    "ChannelWrite",
    "ChannelRead",
    "tools",
    "agent",
    "LangGraph",
    "Branch",
    "branch",
}

_FLOW_AGENT_ALLOW: Set[str] = {
    "router",
    "service",
    "enrollment",
    "notify",
    "guard",
    "final_response",
    "direct_response",
}

_NOISE_LANGGRAPH_NODES: Set[str] = {
    "agent",
    "tools",
}


def resolve_span_filter(value: Optional[str] = None) -> SpanFilterMode:
    raw = value if value is not None else os.environ.get("TRACECAST_SPAN_FILTER", "")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_SPAN_FILTER
    mode = str(raw).strip().lower()
    if mode in ("all", "flow", "llm_tool"):
        return mode  # type: ignore[return-value]
    _logger.warning(
        "TraceCast: unknown span_filter=%r — using %s",
        raw,
        DEFAULT_SPAN_FILTER,
    )
    return DEFAULT_SPAN_FILTER


def bare_span_name(name: Optional[str]) -> str:
    if not name:
        return ""
    if name.startswith("chain:"):
        return name[6:]
    if name.startswith("llm:"):
        return name
    return name


def should_keep_span(span: Span, mode: SpanFilterMode) -> bool:
    if mode == "all":
        return True

    if mode == "llm_tool":
        return span.type in (SpanType.LLM, SpanType.TOOL)

    if span.type in (SpanType.LLM, SpanType.TOOL, SpanType.EMBEDDING, SpanType.AUDIO):
        return True

    meta = span.metadata or {}
    bare = bare_span_name(span.name)
    lg_node = meta.get("langgraph_node")
    if lg_node is not None:
        node = str(lg_node)
        if node in _NOISE_LANGGRAPH_NODES or node in _NOISE_BARE_NAMES:
            return False
        return True

    if meta.get("tc_display"):
        if bare in _NOISE_BARE_NAMES or bare in _NOISE_LANGGRAPH_NODES:
            return False
        return True

    if not bare:
        return False
    if bare in _NOISE_BARE_NAMES or bare in _NOISE_LANGGRAPH_NODES:
        return False
    if bare.startswith("Runnable") or bare.startswith("Channel"):
        return False
    if bare.startswith("route_after_") or bare.startswith("route_by_"):
        return False

    if span.type == SpanType.AGENT:
        if bare.endswith("_node"):
            return True
        if bare in _FLOW_AGENT_ALLOW:
            return True
        if meta.get("tc_order") is not None:
            return True
        return False

    return False


_NODE_ALIASES = {
    "router": "router_node",
    "service": "service_node",
    "guard": "guard_node",
    "enrollment": "enrollment_node",
    "notify": "notify_node",
    "direct_response": "direct_response_node",
    "final_response": "final_response",
}


def _dedupe_key(span: Span) -> str:
    bare = bare_span_name(span.name)
    if span.type in (SpanType.LLM, SpanType.TOOL, SpanType.EMBEDDING, SpanType.AUDIO):
        return f"{span.type.value}:{span.span_id}"
    return _NODE_ALIASES.get(bare, bare)


def _span_rank(span: Span) -> tuple:
    lat = span.latency_ms if span.latency_ms is not None else -1
    has_io = 1 if (span.input or span.output) else 0
    return (lat, has_io)


def dedupe_flow_spans(spans: List[Span]) -> List[Span]:
    """Collapse duplicate agent/node spans (LangGraph often emits 2+ per node)."""
    best: dict = {}
    losers: dict = {}
    passthrough: List[Span] = []

    for span in spans:
        if span.type != SpanType.AGENT:
            passthrough.append(span)
            continue
        key = _dedupe_key(span)
        prev = best.get(key)
        if prev is None:
            best[key] = span
            continue
        if _span_rank(span) >= _span_rank(prev):
            losers[prev.span_id] = span.span_id
            best[key] = span
        else:
            losers[span.span_id] = prev.span_id

    kept = passthrough + list(best.values())
    keep_ids = {s.span_id for s in kept}

    def _resolve(sid: Optional[str]) -> Optional[str]:
        seen: Set[str] = set()
        while sid and sid in losers and sid not in seen:
            seen.add(sid)
            sid = losers[sid]
        return sid

    for span in kept:
        span.parent_span_id = _resolve(span.parent_span_id)
        bare = bare_span_name(span.name)
        canon = _NODE_ALIASES.get(bare)
        if canon and span.type == SpanType.AGENT and bare != canon:
            span.name = canon

    return kept


def filter_spans(spans: List[Span], mode: SpanFilterMode) -> List[Span]:
    if mode == "all" or not spans:
        return spans

    kept: List[Span] = [s for s in spans if should_keep_span(s, mode)]
    if mode == "flow":
        kept = dedupe_flow_spans(kept)

    dropped = len(spans) - len(kept)
    if dropped <= 0 and mode != "flow":
        return kept

    by_id = {s.span_id: s for s in spans}
    keep_ids = {s.span_id for s in kept}

    for span in kept:
        parent = span.parent_span_id
        seen: Set[str] = set()
        while parent and parent not in keep_ids:
            if parent in seen:
                parent = None
                break
            seen.add(parent)
            ancestor = by_id.get(parent)
            parent = ancestor.parent_span_id if ancestor is not None else None
        span.parent_span_id = parent

    _logger.info(
        "TraceCast: span_filter=%s kept=%d dropped=%d names_kept=%s",
        mode,
        len(kept),
        dropped if dropped > 0 else len(spans) - len(kept),
        [s.name for s in kept[:20]],
    )
    return kept


def apply_span_filter_to_trace(trace, mode: SpanFilterMode) -> dict:
    before = len(trace.spans)
    before_names = [s.name for s in trace.spans]
    trace.spans = filter_spans(list(trace.spans), mode)
    after = len(trace.spans)
    dropped_names = [n for n in before_names if n not in {s.name for s in trace.spans}]
    stats = {
        "mode": mode,
        "before": before,
        "after": after,
        "dropped": before - after,
        "kept_names": [s.name for s in trace.spans],
        "dropped_names": dropped_names[:40],
    }
    if before != after:
        _logger.info(
            "TraceCast: trace %s span_filter applied mode=%s %d→%d dropped_sample=%s",
            getattr(trace, "trace_id", "?"),
            mode,
            before,
            after,
            dropped_names[:12],
        )
    return stats
