import asyncio
import functools
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Any
from .core.tracer import Tracer, activate_span
from .models.span import Span, SpanType


_default_tracer: Optional[Tracer] = None


def _truncate(value: Any, limit: int = 2000) -> Optional[str]:
    if value is None:
        return None
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _capture(args: Any, kwargs: Any) -> Any:
    if kwargs and not args:
        return kwargs
    if args and not kwargs:
        return args[0] if len(args) == 1 else args
    return (args, kwargs)


def _new_span(name: str, span_type: SpanType, input_value: Any, order: Optional[float] = None) -> Span:
    metadata: dict = {"tc_display": True}
    if order is not None:
        metadata["tc_order"] = order
    return Span(
        span_id=str(uuid.uuid4()),
        parent_span_id=getattr(Tracer.current_span(), "span_id", None),
        type=span_type,
        name=name,
        started_at=datetime.now(timezone.utc),
        input=_truncate(input_value),
        metadata=metadata,
    )


def trace_span(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    type: SpanType = SpanType.TOOL,
    order: Optional[float] = None,
    capture_io: bool = True,
):
    def decorator(inner_fn: Callable):
        span_name = name or inner_fn.__name__

        if asyncio.iscoroutinefunction(inner_fn):
            @functools.wraps(inner_fn)
            async def async_wrapper(*args: Any, **kwargs: Any):
                trace = Tracer.current()
                if trace is None:
                    return await inner_fn(*args, **kwargs)
                span = _new_span(span_name, type, _capture(args, kwargs) if capture_io else None, order)
                with activate_span(span):
                    try:
                        result = await inner_fn(*args, **kwargs)
                    except Exception as exc:
                        span.finished_at = datetime.now(timezone.utc)
                        span.mark_error(exc)
                        trace.spans.append(span)
                        raise
                span.finished_at = datetime.now(timezone.utc)
                if capture_io:
                    span.output = _truncate(result)
                trace.spans.append(span)
                return result

            return async_wrapper

        @functools.wraps(inner_fn)
        def sync_wrapper(*args: Any, **kwargs: Any):
            trace = Tracer.current()
            if trace is None:
                return inner_fn(*args, **kwargs)
            span = _new_span(span_name, type, _capture(args, kwargs) if capture_io else None, order)
            with activate_span(span):
                try:
                    result = inner_fn(*args, **kwargs)
                except Exception as exc:
                    span.finished_at = datetime.now(timezone.utc)
                    span.mark_error(exc)
                    trace.spans.append(span)
                    raise
            span.finished_at = datetime.now(timezone.utc)
            if capture_io:
                span.output = _truncate(result)
            trace.spans.append(span)
            return result

        return sync_wrapper

    if fn is not None and callable(fn):
        return decorator(fn)
    return decorator


def set_default_tracer(tracer: Tracer) -> None:
    global _default_tracer
    _default_tracer = tracer


def trace_cast(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    tracer: Optional[Tracer] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    if fn is not None and callable(fn):
        return _make_wrapper(
            fn,
            name=name or f"{fn.__module__}.{fn.__qualname__}",
            tracer=tracer,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            metadata=metadata,
        )

    def decorator(inner_fn: Callable):
        return _make_wrapper(
            inner_fn,
            name=name or f"{inner_fn.__module__}.{inner_fn.__qualname__}",
            tracer=tracer,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            metadata=metadata,
        )

    return decorator


def _make_wrapper(
    fn: Callable,
    *,
    name: str,
    tracer: Optional[Tracer],
    session_id: Optional[str],
    user_id: Optional[str],
    project_id: Optional[str],
    metadata: Optional[dict],
):
    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any):
            active_tracer = tracer or _default_tracer or Tracer()
            async with active_tracer.atrace(
                name,
                session_id=session_id,
                user_id=user_id,
                project_id=project_id,
                metadata=metadata,
            ):
                return await fn(*args, **kwargs)

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any):
        active_tracer = tracer or _default_tracer or Tracer()
        with active_tracer.trace(
            name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            metadata=metadata,
        ):
            return fn(*args, **kwargs)

    return sync_wrapper
