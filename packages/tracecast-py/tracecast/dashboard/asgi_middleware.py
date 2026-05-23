"""ASGI middleware that intercepts /tracecast/* requests and delegates to dashboard."""

from typing import Callable, Awaitable
from .reader import TraceReader


class DashboardASGIMiddleware:
    def __init__(
        self,
        app: Callable,
        reader: TraceReader,
        prefix: str = "/tracecast",
    ):
        self.app = app
        self._reader = reader
        self._prefix = prefix

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        path = scope.get("path", "")
        if path.startswith(self._prefix):
            from .router import _make_router
            from fastapi import FastAPI
            sub_app = FastAPI()
            router = _make_router(self._reader)
            sub_app.include_router(router, prefix=self._prefix)
            await sub_app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
