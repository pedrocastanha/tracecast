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


def filter_spans(spans: List[Span], mode: SpanFilterMode) -> List[Span]:
    if mode == "all" or not spans:
        return spans

    kept: List[Span] = [s for s in spans if should_keep_span(s, mode)]
    dropped = len(spans) - len(kept)
    if dropped <= 0:
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
        dropped,
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
