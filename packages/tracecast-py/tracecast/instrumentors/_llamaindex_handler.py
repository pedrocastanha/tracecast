"""LlamaIndex span handler that integrates with TraceCast tracing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class TraceCastSpanHandler:
    """A LlamaIndex span handler that records spans into the active TraceCast trace.

    LlamaIndex's instrumentation dispatcher calls:
      - new_span()             when a span starts
      - prepare_to_exit_span() when a span completes successfully
      - prepare_to_drop_span() when a span is dropped (error)
    """

    def __init__(self) -> None:
        self._open_spans: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # LlamaIndex span handler interface
    # ------------------------------------------------------------------

    def new_span(
        self,
        id_: str,
        bound_args: Any,
        instance: Any,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        from ..core.tracer import Tracer
        from ..models.span import Span, SpanType

        trace = Tracer.current()
        if trace is None:
            return

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llamaindex:span",
            started_at=datetime.now(timezone.utc),
        )
        self._open_spans[id_] = (span, trace)

    def prepare_to_exit_span(
        self,
        id_: str,
        bound_args: Any,
        instance: Any,
        result: Any,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = self._open_spans.pop(id_, None)
        if entry is None:
            return

        span, trace = entry
        span.finished_at = datetime.now(timezone.utc)

        # Try to extract token counts from result.raw if it has usage info
        try:
            raw = result.raw if result is not None else None
            if raw is not None and hasattr(raw, "usage"):
                usage = raw.usage
                if hasattr(usage, "prompt_tokens"):
                    span.tokens_in = int(usage.prompt_tokens)
                if hasattr(usage, "completion_tokens"):
                    span.tokens_out = int(usage.completion_tokens)
        except Exception:
            pass

        trace.spans.append(span)

    def prepare_to_drop_span(
        self,
        id_: str,
        bound_args: Any,
        instance: Any,
        err: Optional[Exception] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = self._open_spans.pop(id_, None)
        if entry is None:
            return

        span, trace = entry
        span.finished_at = datetime.now(timezone.utc)
        if err is not None:
            span.metadata["_error"] = str(err)
        trace.spans.append(span)
