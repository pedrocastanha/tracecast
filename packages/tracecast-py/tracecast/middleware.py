from typing import Callable, Awaitable, Optional
from .core.tracer import Tracer


class TraceCastMiddleware:
    def __init__(
        self,
        app: Callable,
        *,
        tracer: Optional[Tracer] = None,
        name_prefix: str = "",
    ):
        self.app = app
        self._tracer = tracer

        from .decorators import _default_tracer
        self._resolve = lambda: tracer or _default_tracer or Tracer()
        self._name_prefix = name_prefix

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        name = f"{self._name_prefix}{method} {path}"

        tracer = self._resolve()
        async with tracer.atrace(name):
            await self.app(scope, receive, send)
