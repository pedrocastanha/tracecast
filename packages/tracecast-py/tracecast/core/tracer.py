import uuid
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List

from ..models.trace import Trace
from ..exporters.base import BaseExporter


_current_trace: ContextVar[Optional[Trace]] = ContextVar("_current_trace", default=None)


class Tracer:

    def __init__(
        self,
        exporters: Optional[List[BaseExporter]] = None,
        logging: bool = False,
        log_prefix: Optional[str] = None,
    ):
        self.exporters = exporters or []
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

    def _export(self, trace: Trace) -> None:
        for exporter in self.exporters:
            try:
                exporter.export(trace)
            except Exception as exc:
                import warnings
                warnings.warn(f"TraceCast: exporter {type(exporter).__name__} failed: {exc}", stacklevel=2)

    async def _aexport(self, trace: Trace) -> None:
        for exporter in self.exporters:
            try:
                await exporter.aexport(trace)
            except Exception as exc:
                import warnings
                warnings.warn(f"TraceCast: exporter {type(exporter).__name__} failed: {exc}", stacklevel=2)

    @staticmethod
    def current() -> Optional[Trace]:
        return _current_trace.get()
