import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor, active_parent_id


class GeminiInstrumentor(BaseInstrumentor):

    def __init__(self) -> None:
        self._patched: bool = False
        self._original_generate: Optional[Any] = None

    def patch(self) -> None:
        if self._patched:
            return
        import google.generativeai as genai

        self._original_generate = genai.GenerativeModel.generate_content
        _orig = self._original_generate  # snapshot before closure
        self_ref = self

        def patched_generate(model_self, contents, **kwargs):
            # stream pass-through
            if kwargs.get("stream"):
                return _orig(model_self, contents, **kwargs)
            return self_ref._intercept(model_self, contents, kwargs, _orig)

        genai.GenerativeModel.generate_content = patched_generate
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import google.generativeai as genai
        genai.GenerativeModel.generate_content = self._original_generate
        self._original_generate = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, model_self: Any, contents: Any, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(model_self, contents, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content
        from ..core.cost_calculator import calculate_cost
        from ..core.payload import truncate_payload

        model_name = getattr(model_self, "model_name", "unknown")
        input_text = contents if isinstance(contents, str) else str(contents)

        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.LLM,
            name=f"llm:{model_name}",
            model=model_name,
            started_at=datetime.now(timezone.utc),
            input=truncate_payload(input_text),
        )

        try:
            response = original_fn(model_self, contents, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "gemini")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(
            model_name,
            span.tokens_in,
            span.tokens_out,
            tokens_in_cached=span.tokens_in_cached,
        )
        span.output = truncate_payload(extract_content(response, "gemini"))
        trace.spans.append(span)
        return response
