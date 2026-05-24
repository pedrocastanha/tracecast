"""Data access layer for dashboard. Reads traces from configured exporters."""

import json
from pathlib import Path
from typing import List, Optional, Callable
from ..models.trace import Trace
from ..models.span import Span, SpanType
from datetime import datetime


class TraceReader:
    """Reads traces from the Tracer's exporters. Priority: Dict > JsonFile (others via duck typing)."""

    def __init__(self, exporters: list, max_traces: int = 500):
        self._exporters = exporters
        self._max_traces = max_traces
        self._cache: Optional[List[Trace]] = None
        self._cache_ttl = 5.0
        self._last_read = 0.0

    def get_traces(self) -> List[Trace]:
        import time
        now = time.time()
        if self._cache is not None and (now - self._last_read) < self._cache_ttl:
            return self._cache

        traces: List[Trace] = []
        for exporter in self._exporters:
            traces.extend(self._read_from(exporter))

        traces.sort(key=lambda t: t.started_at, reverse=True)
        if len(traces) > self._max_traces:
            traces = traces[:self._max_traces]

        self._cache = traces
        self._last_read = now
        return traces

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        for t in self.get_traces():
            if t.trace_id == trace_id:
                return t
        return None

    def get_sessions(self) -> list:
        from .aggregator import compute_sessions
        return compute_sessions(self.get_traces())

    def get_session(self, session_id: str) -> List[Trace]:
        return [t for t in self.get_traces() if t.session_id == session_id]

    def get_projects(self) -> list:
        from .aggregator import compute_projects
        return compute_projects(self.get_traces())

    def get_project(self, project_id: str) -> List[Trace]:
        return [t for t in self.get_traces() if t.project_id == project_id]

    def _read_from(self, exporter) -> List[Trace]:
        name = type(exporter).__name__

        if "DictExporter" in name:
            return self._from_dict(exporter)

        if "JsonFile" in name:
            return self._from_jsonfile(exporter)

        if "Mongo" in name:
            return self._from_mongo(exporter)

        if "Postgres" in name:
            return self._from_postgres(exporter)

        return []

    def _from_dict(self, exporter) -> List[Trace]:
        raw = getattr(exporter, "traces", [])
        return [_hydrate_trace(d) for d in raw if isinstance(d, dict)]

    def _from_jsonfile(self, exporter) -> List[Trace]:
        path = getattr(exporter, "path", None)
        if not path:
            return []
        fp = Path(path)
        if not fp.exists():
            return []
        traces = []
        with fp.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    traces.append(_hydrate_trace(d))
                except (json.JSONDecodeError, Exception):
                    continue
        return traces

    def _from_mongo(self, exporter) -> List[Trace]:
        try:
            col = getattr(exporter, "_collection", None)
            if col is None:
                return []
            docs = list(col.find().sort("started_at", -1).limit(self._max_traces))
            return [_hydrate_trace(d) for d in docs]
        except Exception:
            return []

    def _from_postgres(self, exporter) -> List[Trace]:
        try:
            conn = getattr(exporter, "_conn", None)
            table = getattr(exporter, "_table", "traces")
            if conn is None:
                return []
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{table}" ORDER BY started_at DESC LIMIT %s',
                (self._max_traces,),
            )
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [_hydrate_trace(dict(zip(cols, row))) for row in rows]
        except Exception:
            return []


def _hydrate_trace(d: dict) -> Trace:
    spans = []
    for s in d.get("spans") or []:
        spans.append(Span(
            span_id=s.get("span_id", s.get("spanId", "")),
            type=SpanType(s.get("type", "llm")),
            name=s.get("name", ""),
            started_at=_parse_dt(s.get("started_at")),
            finished_at=_parse_dt(s.get("finished_at")),
            model=s.get("model"),
            tokens_in=s.get("tokens_in", s.get("tokensIn", 0)),
            tokens_out=s.get("tokens_out", s.get("tokensOut", 0)),
            tokens_in_cached=s.get("tokens_in_cached", s.get("tokensInCached", 0)),
            cost_usd=s.get("cost_usd", s.get("costUsd", 0.0)),
            input=s.get("input"),
            output=s.get("output"),
            metadata=s.get("metadata", {}),
        ))

    return Trace(
        trace_id=d.get("trace_id", d.get("traceId", "")),
        name=d.get("name", "unknown"),
        started_at=_parse_dt(d.get("started_at")) or datetime.now(),
        finished_at=_parse_dt(d.get("finished_at")),
        session_id=d.get("session_id", d.get("sessionId")),
        user_id=d.get("user_id", d.get("userId")),
        project_id=d.get("project_id", d.get("projectId")),
        model=d.get("model"),
        total_tokens_in=d.get("total_tokens_in", d.get("totalTokensIn", 0)),
        total_tokens_out=d.get("total_tokens_out", d.get("totalTokensOut", 0)),
        total_tokens_in_cached=d.get("total_tokens_in_cached", d.get("totalTokensInCached", 0)),
        total_tokens=d.get("total_tokens", d.get("totalTokens", 0)),
        cost_usd=d.get("cost_usd", d.get("costUsd", 0.0)),
        latency_ms=d.get("latency_ms", d.get("latencyMs")),
        tools_used=d.get("tools_used", d.get("toolsUsed", {})),
        spans=spans,
        metadata=d.get("metadata", {}),
    )


def _parse_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        return datetime.fromisoformat(val)
    except (ValueError, AttributeError):
        return None
