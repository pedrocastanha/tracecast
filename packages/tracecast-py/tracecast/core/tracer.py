import asyncio
import os
import random
import threading
import uuid
import contextvars
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Optional, List

from ..models.trace import Trace
from ..models.span import Span
from ..exporters.base import BaseExporter
from .export_queue import (
    ExportWorker,
    default_export_queue_size,
    default_flush_at,
    default_flush_interval,
    default_max_batch_bytes,
)
from .export_stats import ExportStats
from .export_retry import retry_call, default_export_retries, default_export_retry_base
from .trace_summary import build_trace_summary
from .span_filter import resolve_span_filter, apply_span_filter_to_trace, SpanFilterMode


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
        retention_days: Optional[int] = None,
        background_export: bool = False,
        export_queue_size: Optional[int] = None,
        sample_rate: Optional[float] = None,
        flush_at: Optional[int] = None,
        flush_interval: Optional[float] = None,
        max_batch_bytes: Optional[int] = None,
        span_filter: Optional[str] = None,
    ):
        self.exporters = exporters or []
        self.on_export_error = on_export_error
        self.online_eval = online_eval
        self._tc_logger = None
        if logging:
            from .logger import TraceCastLogger
            self._tc_logger = TraceCastLogger(prefix=log_prefix)
        self.blocking_export = blocking_export
        self.retention_days = retention_days
        self.background_export = background_export
        self.sample_rate = self._resolve_sample_rate(sample_rate)
        self.span_filter: SpanFilterMode = resolve_span_filter(span_filter)
        self.stats = ExportStats()
        self._background_tasks: set = set()
        self._export_worker: Optional[ExportWorker] = None
        self._warn_if_sync_persistent()
        if background_export:
            size = export_queue_size if export_queue_size is not None else default_export_queue_size()
            self._export_worker = ExportWorker(
                self._export_batch_items,
                maxsize=size,
                flush_at=flush_at if flush_at is not None else default_flush_at(),
                flush_interval=flush_interval if flush_interval is not None else default_flush_interval(),
                max_batch_bytes=max_batch_bytes if max_batch_bytes is not None else default_max_batch_bytes(),
                on_drop=self._on_queue_drop,
            )

    def _warn_if_sync_persistent(self) -> None:
        if self.background_export:
            return
        risky = {"MongoExporter", "PostgresExporter", "JsonFileExporter", "HttpExporter"}
        names = {type(e).__name__ for e in self.exporters}
        if names & risky:
            import warnings
            warnings.warn(
                "TraceCast: persistent exporter without background_export=True "
                "blocks the request path and risks OOM under load. "
                "Prefer Tracer(..., background_export=True).",
                stacklevel=3,
            )

    def _on_queue_drop(self, _item: Any) -> None:
        self.stats.incr("queue_dropped")

    def export_health(self) -> dict:
        snap = self.stats.snapshot()
        snap["background_export"] = self.background_export
        if self._export_worker is not None:
            snap["queue_size"] = self._export_worker.qsize()
            snap["queue_max"] = self._export_worker.maxsize
            snap["queue_dropped"] = max(snap["queue_dropped"], self._export_worker.dropped)
            snap["queue_spooled"] = getattr(self._export_worker, "spooled", 0)
            snap["spool_path"] = getattr(self._export_worker, "_spool_path", None)
        else:
            snap["queue_size"] = 0
            snap["queue_max"] = 0
            snap["queue_spooled"] = 0
            snap["spool_path"] = None
        return snap

    @staticmethod
    def _resolve_sample_rate(sample_rate: Optional[float]) -> float:
        if sample_rate is not None:
            return max(0.0, min(1.0, float(sample_rate)))
        raw = os.environ.get("TRACECAST_SAMPLE_RATE")
        if raw is None or raw == "":
            return 1.0
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            return 1.0

    def _should_sample(self) -> bool:
        if self.sample_rate >= 1.0:
            return True
        if self.sample_rate <= 0.0:
            return False
        return random.random() < self.sample_rate

    def _run_online_eval(self, trace: Trace) -> None:
        if self.online_eval is None:
            return
        try:
            self.online_eval.maybe_evaluate(trace, default_exporters=self.exporters)
        except Exception:
            from .logger import _logger
            _logger.error("TraceCast: online_eval failed for trace %s", trace.trace_id, exc_info=True)

    def _schedule_online_eval(self, trace: Trace) -> None:
        if self.online_eval is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            threading.Thread(
                target=self._run_online_eval,
                args=(trace,),
                name="tracecast-online-eval",
                daemon=True,
            ).start()
            return

        async def _run():
            await asyncio.to_thread(self._run_online_eval, trace)

        task = loop.create_task(_run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _dispatch_export(self, trace: Trace) -> None:
        if not self._should_sample():
            return
        if self._export_worker is not None:
            self._schedule_online_eval(trace)
            # Enqueue live Trace — serialize/HTTP/disk only on worker threads.
            # Request path: put_nowait only (never blocks user message latency).
            self._export_worker.enqueue(trace)
            return
        self._export(trace)

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
            self._apply_span_filter(t)
            _current_trace.reset(token)
            if self._tc_logger:
                self._tc_logger.trace_end(
                    name,
                    total_tokens=t.total_tokens,
                    cost_usd=t.cost_usd,
                    latency_ms=t.latency_ms,
                    tools_used=t.tools_used,
                )
            self._dispatch_export(t)

    def _apply_span_filter(self, trace: Trace) -> None:
        if self.span_filter == "all":
            return
        apply_span_filter_to_trace(trace, self.span_filter)
        trace.edges = trace._build_edges()

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
            self._apply_span_filter(t)
            _current_trace.reset(token)
            if self._tc_logger:
                self._tc_logger.trace_end(
                    name,
                    total_tokens=t.total_tokens,
                    cost_usd=t.cost_usd,
                    latency_ms=t.latency_ms,
                    tools_used=t.tools_used,
                )
            if not self._should_sample():
                pass
            elif self._export_worker is not None:
                self._schedule_online_eval(t)
                # No to_dict on event loop — worker serializes off-loop.
                self._export_worker.enqueue(t)
            elif self.blocking_export:
                await self._aexport(t)
            else:
                self._schedule_aexport(t)

    def _schedule_aexport(self, trace: Trace) -> None:
        task = asyncio.create_task(self._aexport(trace))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def flush(self, timeout: Optional[float] = None) -> bool:
        if self._export_worker is None:
            return True
        return self._export_worker.flush(timeout=timeout)

    flush_exports = flush

    async def aflush(self, timeout: Optional[float] = None) -> None:
        if self._export_worker is not None:
            await asyncio.to_thread(self._export_worker.flush, timeout)
            return
        pending = list(self._background_tasks)
        if not pending:
            return
        await asyncio.wait(pending, timeout=timeout)

    def _handle_export_error(self, exc: Exception, item: Any, exporter: BaseExporter) -> None:
        from .logger import _logger
        trace_id = item.get("trace_id") if isinstance(item, dict) else getattr(item, "trace_id", "?")
        _logger.warning(
            "TraceCast: exporter %s failed for trace %s: %s",
            type(exporter).__name__, trace_id, exc,
        )
        self.stats.set_last_error(f"{type(exporter).__name__}: {exc}")
        if self.on_export_error is not None and isinstance(item, Trace):
            try:
                self.on_export_error(exc, item, exporter)
            except Exception:
                _logger.exception("TraceCast: on_export_error hook raised")

    def _try_summary(self, source: Any, exc: Exception, exporter: BaseExporter) -> None:
        from .logger import _logger
        try:
            summary = build_trace_summary(source, exc)
            exporter.export_summary(summary)
            self.stats.incr("summary_fallback")
        except Exception as summary_exc:
            self.stats.incr("export_failed")
            _logger.warning(
                "TraceCast: summary fallback also failed on %s: %s",
                type(exporter).__name__, summary_exc,
            )

    def _export_one_with_retry(self, exporter: BaseExporter, write_fn: Callable[[], None], source: Any) -> bool:
        attempts = default_export_retries()
        base = default_export_retry_base()

        def on_retry(_i: int, _exc: BaseException) -> None:
            self.stats.incr("export_retried")

        try:
            retry_call(write_fn, attempts=attempts, base_delay=base, on_retry=on_retry)
            self.stats.incr("exported_ok")
            return True
        except Exception as exc:
            self._handle_export_error(exc, source if isinstance(source, Trace) else source, exporter)
            self._try_summary(source, exc, exporter)
            return False

    def _export(self, trace: Trace) -> None:
        any_ok = False
        for exporter in self.exporters:
            if self._export_one_with_retry(exporter, lambda e=exporter: e.export(trace), trace):
                any_ok = True
        if any_ok:
            self._run_online_eval(trace)

    def _export_batch_items(self, items: List[Any]) -> None:
        if not items:
            return
        docs = [i if isinstance(i, dict) else i.to_dict() for i in items]
        for exporter in self.exporters:
            attempts = default_export_retries()
            base = default_export_retry_base()

            def on_retry(_i: int, _exc: BaseException) -> None:
                self.stats.incr("export_retried")

            try:
                retry_call(
                    lambda e=exporter, d=docs: e.export_docs_batch(d),
                    attempts=attempts,
                    base_delay=base,
                    on_retry=on_retry,
                )
                self.stats.incr("exported_ok", len(docs))
            except Exception as batch_exc:
                self._handle_export_error(batch_exc, docs[0] if docs else {}, exporter)
                for doc in docs:
                    try:
                        retry_call(
                            lambda e=exporter, d=doc: e.export_doc(d),
                            attempts=max(1, attempts - 1),
                            base_delay=base,
                            on_retry=on_retry,
                        )
                        self.stats.incr("exported_ok")
                    except Exception as item_exc:
                        self._try_summary(doc, item_exc, exporter)

    async def _aexport(self, trace: Trace) -> None:
        any_ok = False
        attempts = default_export_retries()
        base = default_export_retry_base()
        for exporter in self.exporters:
            last_exc: Optional[Exception] = None
            for i in range(attempts):
                try:
                    await exporter.aexport(trace)
                    self.stats.incr("exported_ok")
                    any_ok = True
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if i + 1 < attempts:
                        self.stats.incr("export_retried")
                        await asyncio.sleep(base * (2 ** i) * 0.5)
            if last_exc is not None:
                self._handle_export_error(last_exc, trace, exporter)
                await asyncio.to_thread(self._try_summary, trace, last_exc, exporter)
        if any_ok:
            await asyncio.to_thread(self._run_online_eval, trace)

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
        retention_days: Optional[int] = None,
    ):
        if retention_days is not None:
            self.retention_days = retention_days
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
        reader = TraceReader(self.exporters, max_traces=max_traces, retention_days=self.retention_days)
        reader.export_stats_provider = self.export_health
        self._attach_ingest(reader)

        try:
            from fastapi import FastAPI
            if isinstance(app, FastAPI):
                from ..dashboard.router import _make_router
                router = _make_router(reader, prefix=prefix)
                app.include_router(router, prefix=prefix)
                if self.retention_days:
                    from ..exporters.mongo import MongoExporter
                    mongo_exporters = [e for e in self.exporters if isinstance(e, MongoExporter)]
                    if mongo_exporters:
                        from ..dashboard.retention import retention_loop

                        retention_started = {"done": False}

                        @app.middleware("http")
                        async def _start_retention_once(request, call_next):
                            if not retention_started["done"]:
                                retention_started["done"] = True
                                for exp in mongo_exporters:
                                    task = asyncio.create_task(retention_loop(exp, self.retention_days))
                                    self._background_tasks.add(task)
                                    task.add_done_callback(self._background_tasks.discard)
                            return await call_next(request)
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

    def _attach_ingest(self, reader) -> None:
        """Enable POST /api/ingest on this reader when env allows and exporters exist."""
        raw = os.environ.get("TRACECAST_INGEST", "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return
        if not self.exporters:
            return
        # Avoid double-attach
        if getattr(reader, "ingest", None) is not None:
            return
        from .ingest import IngestService

        exporters = list(self.exporters)

        def _store_write(docs):
            for exp in exporters:
                try:
                    exp.export_docs_batch(docs)
                except Exception:
                    # Per-exporter: best effort; IngestService catches total failure
                    raise

        reader.ingest = IngestService(_store_write)
        # Keep handle for flush/shutdown if needed later
        self._ingest_service = reader.ingest

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
        reader.export_stats_provider = self.export_health
        self._attach_ingest(reader)
        serve_dashboard(reader, host=host, port=port, prefix=prefix)
