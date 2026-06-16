import uuid
import contextvars
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Optional, List

from ..models.trace import Trace
from ..models.span import Span
from ..exporters.base import BaseExporter


_current_trace: ContextVar[Optional[Trace]] = ContextVar("_current_trace", default=None)
_current_span: ContextVar[Optional[Span]] = ContextVar("_current_span", default=None)


@contextmanager
def activate_span(span: Span):
    token = _current_span.set(span)
    try:
        yield span
    finally:
        _current_span.reset(token)


def bind_context(fn: Callable, *args: Any, **kwargs: Any) -> Callable[[], Any]:
    ctx = contextvars.copy_context()

    def _runner() -> Any:
        return ctx.run(fn, *args, **kwargs)

    return _runner


class Tracer:

    def __init__(
        self,
        exporters: Optional[List[BaseExporter]] = None,
        logging: bool = False,
        log_prefix: Optional[str] = None,
        on_export_error: Optional[Callable[[Exception, Trace, BaseExporter], None]] = None,
    ):
        self.exporters = exporters or []
        self.on_export_error = on_export_error
        self._tc_logger = None
        if logging:
            from .logger import TraceCastLogger
            self._tc_logger = TraceCastLogger(prefix=log_prefix)

    @contextmanager
    def trace(self, name: str, session_id=None, user_id=None, project_id=None, metadata=None):
        t = Trace(
            trace_id=str(uuid.uuid4()),
            name=name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            started_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        if self._tc_logger:
            self._tc_logger.trace_start(name)
        token = _current_trace.set(t)
        try:
            yield t
        finally:
            t.finished_at = datetime.now(timezone.utc)
            t._finalize()
            _current_trace.reset(token)
            if self._tc_logger:
                self._tc_logger.trace_end(
                    name,
                    total_tokens=t.total_tokens,
                    cost_usd=t.cost_usd,
                    latency_ms=t.latency_ms,
                    tools_used=t.tools_used,
                )
            self._export(t)

    @asynccontextmanager
    async def atrace(self, name: str, session_id=None, user_id=None, project_id=None, metadata=None):
        t = Trace(
            trace_id=str(uuid.uuid4()),
            name=name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            started_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        if self._tc_logger:
            self._tc_logger.trace_start(name)
        token = _current_trace.set(t)
        try:
            yield t
        finally:
            t.finished_at = datetime.now(timezone.utc)
            t._finalize()
            _current_trace.reset(token)
            if self._tc_logger:
                self._tc_logger.trace_end(
                    name,
                    total_tokens=t.total_tokens,
                    cost_usd=t.cost_usd,
                    latency_ms=t.latency_ms,
                    tools_used=t.tools_used,
                )
            await self._aexport(t)

    def _handle_export_error(self, exc: Exception, trace: Trace, exporter: BaseExporter) -> None:
        from .logger import _logger
        _logger.error(
            "TraceCast: exporter %s failed for trace %s: %s",
            type(exporter).__name__, trace.trace_id, exc,
            exc_info=True,
        )
        if self.on_export_error is not None:
            try:
                self.on_export_error(exc, trace, exporter)
            except Exception:
                _logger.exception("TraceCast: on_export_error hook raised")

    def _export(self, trace: Trace) -> None:
        for exporter in self.exporters:
            try:
                exporter.export(trace)
            except Exception as exc:
                self._handle_export_error(exc, trace, exporter)

    async def _aexport(self, trace: Trace) -> None:
        for exporter in self.exporters:
            try:
                await exporter.aexport(trace)
            except Exception as exc:
                self._handle_export_error(exc, trace, exporter)

    @staticmethod
    def current() -> Optional[Trace]:
        return _current_trace.get()

    @staticmethod
    def current_span() -> Optional[Span]:
        return _current_span.get()

    def mount(
        self,
        app,
        prefix: str = "/tracecast",
        read_only: bool = True,
        auth: Optional[tuple] = None,
        max_traces: int = 500,
    ):
        if not self.exporters:
            import warnings
            from ..exporters.dict_exporter import DictExporter
            self.exporters = [DictExporter()]
            warnings.warn(
                "TraceCast: No exporter configured. Using in-memory storage. "
                "Data will be lost on restart. Configure a persistent exporter "
                "(JsonFileExporter, MongoExporter, PostgresExporter) for production.",
                stacklevel=2,
            )

        from ..dashboard.reader import TraceReader
        reader = TraceReader(self.exporters, max_traces=max_traces)

        try:
            from fastapi import FastAPI
            if isinstance(app, FastAPI):
                from ..dashboard.router import _make_router
                router = _make_router(reader, prefix=prefix)
                app.include_router(router, prefix=prefix)
                return
        except ImportError:
            pass

        try:
            from flask import Flask
            if isinstance(app, Flask):
                from ..dashboard.blueprint import _make_blueprint
                bp = _make_blueprint(reader, prefix=prefix)
                app.register_blueprint(bp)
                return
        except ImportError:
            pass

        from ..dashboard.asgi_middleware import DashboardASGIMiddleware
        middleware = DashboardASGIMiddleware(app, reader, prefix=prefix)
        import warnings
        warnings.warn(
            "TraceCast: Could not auto-detect framework. Wrapping as ASGI middleware. "
            "If mount() returns a new app instance, reassign it: app = tracer.mount(app)",
            stacklevel=2,
        )
        return middleware

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 7777,
        prefix: str = "/tracecast",
        max_traces: int = 500,
    ):
        from ..dashboard.reader import TraceReader
        from ..dashboard.standalone import serve_dashboard
        reader = TraceReader(self.exporters, max_traces=max_traces)
        serve_dashboard(reader, host=host, port=port, prefix=prefix)
