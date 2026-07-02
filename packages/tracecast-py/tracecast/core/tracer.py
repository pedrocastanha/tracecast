import asyncio
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


def push_span(span: Span):
    """Set span as current without a context manager. Returns reset token."""
    return _current_span.set(span)


def pop_span(token) -> None:
    """Restore previous current span using token from push_span."""
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
        online_eval=None,
        blocking_export: bool = False,
    ):
        self.exporters = exporters or []
        self.on_export_error = on_export_error
        self.online_eval = online_eval
        self._tc_logger = None
        if logging:
            from .logger import TraceCastLogger
            self._tc_logger = TraceCastLogger(prefix=log_prefix)
        self.blocking_export = blocking_export
        self._background_tasks: set = set()

    def _run_online_eval(self, trace: Trace) -> None:
        if self.online_eval is None:
            return
        try:
            self.online_eval.maybe_evaluate(trace, default_exporters=self.exporters)
        except Exception:
            from .logger import _logger
            _logger.error("TraceCast: online_eval failed for trace %s", trace.trace_id, exc_info=True)

    @contextmanager
    def trace(self, name: str, session_id=None, user_id=None, project_id=None, project_name=None, metadata=None):
        t = Trace(
            trace_id=str(uuid.uuid4()),
            name=name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            project_name=project_name,
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
    async def atrace(self, name: str, session_id=None, user_id=None, project_id=None, project_name=None, metadata=None):
        t = Trace(
            trace_id=str(uuid.uuid4()),
            name=name,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            project_name=project_name,
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
            if self.blocking_export:
                await self._aexport(t)
            else:
                self._schedule_aexport(t)

    def _schedule_aexport(self, trace: Trace) -> None:
        task = asyncio.create_task(self._aexport(trace))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def aflush(self, timeout: Optional[float] = None) -> None:
        pending = list(self._background_tasks)
        if not pending:
            return
        await asyncio.wait(pending, timeout=timeout)

    def _handle_export_error(self, exc: Exception, trace: Trace, exporter: BaseExporter) -> None:
        from .logger import _logger
        _logger.warning(
            "TraceCast: exporter %s failed for trace %s: %s",
            type(exporter).__name__, trace.trace_id, exc,
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
        self._run_online_eval(trace)

    async def _aexport(self, trace: Trace) -> None:
        for exporter in self.exporters:
            try:
                await exporter.aexport(trace)
            except Exception as exc:
                self._handle_export_error(exc, trace, exporter)
        self._run_online_eval(trace)

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
