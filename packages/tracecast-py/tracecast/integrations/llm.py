import inspect
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar
from ..core.tracer import Tracer
from ..core.token_counter import extract_tokens, extract_content, extract_input_text
from ..core.cost_calculator import calculate_cost
from ..core.payload import truncate_payload
from ..models.span import Span, SpanType

T = TypeVar("T")


def trace_llm_call(
    fn: Callable[..., T],
    *,
    provider: str,
    model: str,
    input_text: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> T:
    trace = Tracer.current()
    if trace is None:
        return fn()

    span = Span(
        span_id=str(uuid.uuid4()),
        parent_span_id=getattr(Tracer.current_span(), "span_id", None),
        type=SpanType.LLM,
        name=f"llm:{model}",
        model=model,
        started_at=datetime.now(timezone.utc),
        input=truncate_payload(input_text),
        metadata=metadata or {},
    )

    tracer = _resolve_tracer()
    logger = getattr(tracer, "_tc_logger", None)
    if logger:
        logger.llm_start(trace.name, model=model)

    response: Any = None
    error: Optional[str] = None
    try:
        response = fn()
    except Exception as exc:
        error = str(exc)
        if logger:
            logger.llm_error(trace.name, model=model, error=error)
        span.finished_at = datetime.now(timezone.utc)
        span.mark_error(exc)
        trace.spans.append(span)
        raise

    span.finished_at = datetime.now(timezone.utc)
    tokens = extract_tokens(response, provider)
    span.tokens_in = int(tokens["input"])
    span.tokens_out = int(tokens["output"])
    span.tokens_in_cached = int(tokens.get("cached", 0))
    span.cost_usd = calculate_cost(
        model,
        span.tokens_in,
        span.tokens_out,
        tokens_in_cached=span.tokens_in_cached,
    )
    span.output = truncate_payload(extract_content(response, provider))
    trace.spans.append(span)

    if logger:
        latency_ms = None
        if span.finished_at and span.started_at:
            latency_ms = (span.finished_at - span.started_at).total_seconds() * 1000
        logger.llm_end(
            trace.name,
            model=model,
            tokens_in=span.tokens_in,
            tokens_out=span.tokens_out,
            tokens_in_cached=span.tokens_in_cached,
            cost_usd=span.cost_usd,
            latency_ms=latency_ms,
        )

    return response


async def _async_trace_llm_call(
    coro,
    *,
    provider: str,
    model: str,
    input_text: Optional[str] = None,
):
    """Async counterpart of trace_llm_call — properly awaits the API response."""
    trace = Tracer.current()
    if trace is None:
        return await coro

    span = Span(
        span_id=str(uuid.uuid4()),
        parent_span_id=getattr(Tracer.current_span(), "span_id", None),
        type=SpanType.LLM,
        name=f"llm:{model}",
        model=model,
        started_at=datetime.now(timezone.utc),
        input=truncate_payload(input_text),
        metadata={},
    )
    tracer = _resolve_tracer()
    logger = getattr(tracer, "_tc_logger", None)
    if logger:
        logger.llm_start(trace.name, model=model)

    try:
        response = await coro
    except Exception as exc:
        span.finished_at = datetime.now(timezone.utc)
        span.mark_error(exc)
        trace.spans.append(span)
        if logger:
            logger.llm_error(trace.name, model=model, error=str(exc))
        raise

    span.finished_at = datetime.now(timezone.utc)
    tokens = extract_tokens(response, provider)
    span.tokens_in = int(tokens["input"])
    span.tokens_out = int(tokens["output"])
    span.tokens_in_cached = int(tokens.get("cached", 0))
    span.cost_usd = calculate_cost(
        model,
        span.tokens_in,
        span.tokens_out,
        tokens_in_cached=span.tokens_in_cached,
    )
    span.output = truncate_payload(extract_content(response, provider))
    trace.spans.append(span)

    if logger:
        latency_ms = (span.finished_at - span.started_at).total_seconds() * 1000
        logger.llm_end(
            trace.name,
            model=model,
            tokens_in=span.tokens_in,
            tokens_out=span.tokens_out,
            tokens_in_cached=span.tokens_in_cached,
            cost_usd=span.cost_usd,
            latency_ms=latency_ms,
        )
    return response


def _resolve_tracer() -> Tracer:
    from ..decorators import _default_tracer
    return _default_tracer or Tracer()


def wrap_openai(client: Any) -> Any:
    return _ProxyWrapper(client, provider="openai", intercept_attr="chat.completions.create")


def wrap_anthropic(client: Any) -> Any:
    return _ProxyWrapper(client, provider="anthropic", intercept_attr="messages.create")


class _ProxyWrapper:
    __slots__ = ("_client", "_provider", "_intercept_path")

    def __init__(self, client: Any, *, provider: str, intercept_attr: str):
        self._client = client
        self._provider = provider
        self._intercept_path = intercept_attr.split(".")

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._client, name)
        if name == self._intercept_path[0]:
            return _NestedProxy(
                target,
                provider=self._provider,
                intercept_rest=self._intercept_path[1:],
            )
        return target


class _NestedProxy:
    __slots__ = ("_target", "_provider", "_intercept_rest")

    def __init__(self, target: Any, *, provider: str, intercept_rest: list):
        self._target = target
        self._provider = provider
        self._intercept_rest = intercept_rest

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._target, name)
        if self._intercept_rest and name == self._intercept_rest[0]:
            return _NestedProxy(
                target,
                provider=self._provider,
                intercept_rest=self._intercept_rest[1:],
            )
        return target

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, self._provider)
        raw = self._target(*args, **kwargs)
        if inspect.isawaitable(raw):
            return _async_trace_llm_call(
                raw,
                provider=self._provider,
                model=model,
                input_text=input_text,
            )
        return trace_llm_call(
            lambda: raw,
            provider=self._provider,
            model=model,
            input_text=input_text,
        )
