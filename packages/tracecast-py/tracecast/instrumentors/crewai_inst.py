"""CrewAI instrumentor using monkey-patching on crewai.Crew.kickoff."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .base import BaseInstrumentor


class CrewAIInstrumentor(BaseInstrumentor):
    """Instruments CrewAI by patching Crew.kickoff to capture agent spans.

    Usage::

        inst = CrewAIInstrumentor()
        inst.patch()          # all subsequent Crew.kickoff calls are captured
        ...
        inst.unpatch()        # restores the original method
    """

    def __init__(self) -> None:
        self._patched: bool = False
        self._original_kickoff: Optional[Any] = None

    def patch(self) -> None:
        if self._patched:
            return

        import crewai

        self._original_kickoff = crewai.Crew.kickoff
        _orig = self._original_kickoff  # snapshot before closure
        self_ref = self

        def patched_kickoff(crew_self, inputs=None, **kwargs):
            return self_ref._intercept(crew_self, inputs, kwargs, _orig)

        crewai.Crew.kickoff = patched_kickoff
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return

        import crewai

        crewai.Crew.kickoff = self._original_kickoff
        self._original_kickoff = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, crew_self: Any, inputs: Any, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer

        trace = Tracer.current()
        if trace is None:
            return original_fn(crew_self, inputs=inputs, **kwargs)
        return self._capture(crew_self, inputs, kwargs, original_fn, trace)

    def _capture(self, crew_self: Any, inputs: Any, kwargs: dict, original_fn: Any, trace: Any) -> Any:
        from ..models.span import Span, SpanType

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.AGENT,
            name="crewai:kickoff",
            started_at=datetime.now(timezone.utc),
        )

        try:
            result = original_fn(crew_self, inputs=inputs, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)

        # Extract token counts from result.token_usage if available
        try:
            if result is not None and hasattr(result, "token_usage") and result.token_usage is not None:
                token_usage = result.token_usage
                if hasattr(token_usage, "prompt_tokens"):
                    span.tokens_in = int(token_usage.prompt_tokens)
                if hasattr(token_usage, "completion_tokens"):
                    span.tokens_out = int(token_usage.completion_tokens)
        except Exception:
            pass

        trace.spans.append(span)
        return result
