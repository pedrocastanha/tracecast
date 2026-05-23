import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor


class OpenAIInstrumentor(BaseInstrumentor):

    def __init__(self) -> None:
        self._original_create: Optional[Any] = None
        self._original_acreate: Optional[Any] = None
        self._patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        import openai.resources.chat.completions as mod

        # Sync
        self._original_create = mod.Completions.create
        self_ref = self
        _orig_create = self._original_create

        def patched_create(client_self, *args, **kwargs):
            return self_ref._intercept(client_self, args, kwargs, _orig_create)

        mod.Completions.create = patched_create

        # Async
        if hasattr(mod, "AsyncCompletions"):
            self._original_acreate = mod.AsyncCompletions.create
            _orig_acreate = self._original_acreate

            async def patched_acreate(client_self, *args, **kwargs):
                return await self_ref._async_intercept(client_self, args, kwargs, _orig_acreate)

            mod.AsyncCompletions.create = patched_acreate

        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import openai.resources.chat.completions as mod
        mod.Completions.create = self._original_create
        if hasattr(mod, "AsyncCompletions") and self._original_acreate is not None:
            mod.AsyncCompletions.create = self._original_acreate
        self._original_create = None
        self._original_acreate = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(client_self, *args, **kwargs)
        return self._capture(client_self, args, kwargs, original_fn, trace)

    def _capture(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any, trace: Any) -> Any:
        # Streaming not yet supported — pass through untracked
        if kwargs.get("stream"):
            return original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "openai")

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=input_text,
        )

        try:
            response = original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "openai")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(
            model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached
        )
        span.output = extract_content(response, "openai")
        trace.spans.append(span)

        return response

    async def _async_intercept(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return await original_fn(client_self, *args, **kwargs)
        return await self._async_capture(client_self, args, kwargs, original_fn, trace)

    async def _async_capture(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any, trace: Any) -> Any:
        # Streaming not yet supported — pass through untracked
        if kwargs.get("stream"):
            return await original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "openai")

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=input_text,
        )

        try:
            response = await original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "openai")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(
            model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached
        )
        span.output = extract_content(response, "openai")
        trace.spans.append(span)
        return response
