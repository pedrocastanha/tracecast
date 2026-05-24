"""LlamaIndex span handler that integrates with TraceCast tracing.

Two classes are provided here:

* ``TraceCastSpanHandler`` – a plain Python class used by the test suite
  (which injects a fake ``llama_index`` module via ``sys.modules``).  It
  deliberately does **not** subclass ``BaseSpanHandler`` so that it can be
  imported without LlamaIndex being installed.

* ``_build_handler_class()`` – a factory that, when LlamaIndex **is**
  installed, returns a proper ``BaseSpanHandler[SimpleSpan]`` subclass
  (required by ``dispatcher.add_span_handler()``).  The factory is called
  lazily by ``LlamaIndexInstrumentor.patch()``.

LlamaIndex (>= 0.10 / ``llama-index-instrumentation`` package) ships
``BaseSpanHandler`` at::

    llama_index_instrumentation.span_handlers.base.BaseSpanHandler

The ``add_span_handler`` signature confirms the expected type::

    (handler: llama_index_instrumentation.span_handlers.base.BaseSpanHandler) -> None
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Plain class – used directly by tests (fake llama_index via sys.modules)
# ---------------------------------------------------------------------------

class TraceCastSpanHandler:
    """A LlamaIndex span handler that records spans into the active TraceCast trace.

    LlamaIndex's instrumentation dispatcher calls:
      - new_span()             when a span starts
      - prepare_to_exit_span() when a span completes successfully
      - prepare_to_drop_span() when a span is dropped (error)

    NOTE: This plain class does **not** subclass ``BaseSpanHandler`` so that it
    can be imported in test environments where LlamaIndex is absent.  In real
    usage ``LlamaIndexInstrumentor.patch()`` uses ``_build_handler_class()``
    (see below) which returns the proper Pydantic-based subclass required by
    the dispatcher.
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
        instance: Any = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        from ..core.tracer import Tracer
        from ..models.span import Span, SpanType

        trace = Tracer.current()
        if trace is None:
            return

        instance_name = type(instance).__name__ if instance is not None else "span"
        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llamaindex:{instance_name}",
            started_at=datetime.now(timezone.utc),
        )
        self._open_spans[id_] = (span, trace)

    def prepare_to_exit_span(
        self,
        id_: str,
        bound_args: Any = None,
        instance: Any = None,
        result: Any = None,
        **kwargs: Any,
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
        bound_args: Any = None,
        instance: Any = None,
        err: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        entry = self._open_spans.pop(id_, None)
        if entry is None:
            return

        span, trace = entry
        span.finished_at = datetime.now(timezone.utc)
        if err is not None:
            span.metadata["_error"] = str(err)
        trace.spans.append(span)


# ---------------------------------------------------------------------------
# Factory – returns a proper BaseSpanHandler subclass when LlamaIndex is real
# ---------------------------------------------------------------------------

def _build_handler_class():
    """Return a ``BaseSpanHandler[SimpleSpan]`` subclass for real LlamaIndex usage.

    The installed version ships ``BaseSpanHandler`` at::

        llama_index_instrumentation.span_handlers.base.BaseSpanHandler

    which is a Pydantic ``BaseModel`` generic.  We must subclass it (not just
    duck-type it) because ``dispatcher.add_span_handler()`` validates the type.

    This function is called lazily by ``LlamaIndexInstrumentor.patch()`` so
    that tests which inject a fake ``llama_index`` module are unaffected.

    Returns
    -------
    type
        A concrete subclass of ``BaseSpanHandler[SimpleSpan]``.
    """
    # Primary location (llama-index >= 0.10 / llama-index-instrumentation pkg)
    try:
        from llama_index_instrumentation.span_handlers.base import BaseSpanHandler
        from llama_index_instrumentation.span.simple import SimpleSpan
    except ImportError:
        # Older monolithic llama_index layout (< 0.10) – fall back gracefully
        from llama_index.core.instrumentation.span_handlers.base import BaseSpanHandler  # type: ignore[no-redef]
        from llama_index.core.instrumentation.span.simple import SimpleSpan  # type: ignore[no-redef]

    class _TraceCastSpanHandlerReal(BaseSpanHandler[SimpleSpan]):
        """Proper BaseSpanHandler subclass for production LlamaIndex usage."""

        model_config = {"arbitrary_types_allowed": True}

        # Private storage for in-flight spans; stored as a plain dict on the
        # instance (Pydantic private attr would require PrivateAttr declaration).
        def model_post_init(self, __context: Any) -> None:
            object.__setattr__(self, "_open_spans", {})

        def new_span(
            self,
            id_: str,
            bound_args: Any,
            instance: Any = None,
            parent_span_id: Optional[str] = None,
            tags: Optional[Dict[str, Any]] = None,
            **kwargs: Any,
        ) -> Optional[SimpleSpan]:
            from ..core.tracer import Tracer
            from ..models.span import Span, SpanType

            trace = Tracer.current()
            if trace is None:
                return SimpleSpan(id_=id_, parent_id=parent_span_id)

            instance_name = type(instance).__name__ if instance is not None else "span"
            span = Span(
                span_id=id_ or str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llamaindex:{instance_name}",
                started_at=datetime.now(timezone.utc),
            )
            self._open_spans[id_] = (span, trace)
            return SimpleSpan(id_=id_, parent_id=parent_span_id)

        def prepare_to_exit_span(
            self,
            id_: str,
            bound_args: Any = None,
            instance: Any = None,
            result: Any = None,
            **kwargs: Any,
        ) -> Optional[SimpleSpan]:
            entry = self._open_spans.pop(id_, None)
            if entry is None:
                return None

            span, trace = entry
            span.finished_at = datetime.now(timezone.utc)

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
            return None

        def prepare_to_drop_span(
            self,
            id_: str,
            bound_args: Any = None,
            instance: Any = None,
            err: Optional[BaseException] = None,
            **kwargs: Any,
        ) -> Optional[SimpleSpan]:
            entry = self._open_spans.pop(id_, None)
            if entry is None:
                return None

            span, trace = entry
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(err) if err else "dropped"
            trace.spans.append(span)
            return None

    return _TraceCastSpanHandlerReal
