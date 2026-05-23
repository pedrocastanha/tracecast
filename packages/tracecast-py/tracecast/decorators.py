import asyncio
import functools
from typing import Callable, Optional, Any
from .core.tracer import Tracer


_default_tracer: Optional[Tracer] = None


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
    active_tracer = tracer or _default_tracer or Tracer()

    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any):
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
        with active_tracer.trace(
            name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            metadata=metadata,
        ):
            return fn(*args, **kwargs)

    return sync_wrapper
