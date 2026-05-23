"""Standalone server for dashboard without any existing web framework."""

from .reader import TraceReader


def serve_dashboard(
    reader: TraceReader,
    host: str = "127.0.0.1",
    port: int = 7777,
    prefix: str = "/tracecast",
):
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        raise ImportError(
            "Dashboard standalone server requires uvicorn and fastapi. "
            "Install with: pip install uvicorn fastapi"
        )

    from .router import _make_router

    app = FastAPI()
    router = _make_router(reader)
    app.include_router(router, prefix=prefix)

    print(f"TraceCast Dashboard → http://{host}:{port}{prefix}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
