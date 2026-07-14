"""Standalone server for dashboard without any existing web framework."""

import base64
import secrets
from typing import Optional, Tuple, List

from .reader import TraceReader


def _build_app(
    reader: TraceReader,
    prefix: str,
    auth: Optional[Tuple[str, str]] = None,
    cors_origins: Optional[List[str]] = None,
):
    from fastapi import FastAPI, Request
    from fastapi.responses import Response
    from .router import _make_router

    app = FastAPI()

    if cors_origins:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    if auth:
        expected_user, expected_pass = auth

        @app.middleware("http")
        async def _basic_auth(request: Request, call_next):
            header = request.headers.get("authorization", "")
            if header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:]).decode("utf-8")
                    user, _, password = decoded.partition(":")
                    if secrets.compare_digest(user, expected_user) and secrets.compare_digest(password, expected_pass):
                        return await call_next(request)
                except Exception:
                    pass
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="TraceCast"'},
            )

    router = _make_router(reader, prefix=prefix)
    app.include_router(router, prefix=prefix)
    return app


def serve_dashboard(
    reader: TraceReader,
    host: str = "127.0.0.1",
    port: int = 7777,
    prefix: str = "/tracecast",
    auth: Optional[Tuple[str, str]] = None,
    cors_origins: Optional[List[str]] = None,
):
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "Dashboard standalone server requires uvicorn and fastapi. "
            "Install with: pip install uvicorn fastapi"
        )

    app = _build_app(reader, prefix=prefix, auth=auth, cors_origins=cors_origins)
    print(f"TraceCast Dashboard → http://{host}:{port}{prefix}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
