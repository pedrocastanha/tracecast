"""Data access layer for dashboard. Reads traces from configured exporters."""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Callable, Any
from ..models.trace import Trace
from ..models.span import Span, SpanType, SpanStatus
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger("tracecast")

DEFAULT_METRICS_WINDOW = timedelta(hours=24)
DEFAULT_METRICS_MAX_TRACES = 1000
_DEAD_EXPORTER_TTL = 60.0


def _metrics_max_traces() -> int:
    import os
    raw = os.environ.get("TRACECAST_METRICS_MAX_TRACES")
    if raw is None or raw == "":
        return DEFAULT_METRICS_MAX_TRACES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_METRICS_MAX_TRACES


class TraceReader:
    def __init__(self, exporters: list, max_traces: int = 500, retention_days: Optional[int] = None):
        self._exporters = exporters
        self._max_traces = max_traces
        self.retention_days = retention_days
        self._cache: Optional[List[Trace]] = None
        self._cache_ttl = 5.0
        self._last_read = 0.0
        self.export_stats_provider: Optional[Callable[[], dict]] = None
        self.ingest: Any = None  # optional IngestService for POST /api/ingest
        self._dead_until: dict = {}

    def _mark_dead(self, exporter) -> None:
        self._dead_until[id(exporter)] = time.monotonic() + _DEAD_EXPORTER_TTL
        _logger.warning(
            "TraceCast: exporter %s marked unavailable for %.0fs (read path will skip it)",
            type(exporter).__name__,
            _DEAD_EXPORTER_TTL,
        )

    def _is_alive(self, exporter) -> bool:
        until = self._dead_until.get(id(exporter))
        if until is None:
            return True
        if time.monotonic() >= until:
            self._dead_until.pop(id(exporter), None)
            return True
        return False

    def get_traces(self) -> List[Trace]:
        now = time.time()
        if self._cache is not None and (now - self._last_read) < self._cache_ttl:
            return self._cache

        traces: List[Trace] = []
        for exporter in self._exporters:
            if not self._is_alive(exporter):
                continue
            try:
                traces.extend(self._read_from(exporter))
            except Exception:
                self._mark_dead(exporter)

        traces.sort(key=lambda t: t.started_at, reverse=True)
        if len(traces) > self._max_traces:
            traces = traces[:self._max_traces]

        self._cache = traces
        self._last_read = now
        return traces

    def _readable(self):
        for exporter in self._exporters:
            if not self._is_alive(exporter):
                continue
            if callable(getattr(exporter, "query", None)):
                return exporter
        return None

    def _queryable(self):
        for exporter in self._exporters:
            if not self._is_alive(exporter):
                continue
            if callable(getattr(exporter, "query", None)):
                yield exporter

    def query_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt=None,
        to_dt=None,
        sort_by: str = "date",
        order: str = "desc",
    ):
        offset = (max(page, 1) - 1) * page_size
        for exporter in self._queryable():
            try:
                rows = exporter.query(
                    project_name=project_name, project_id=project_id, user_id=user_id, session_id=session_id,
                    from_dt=from_dt, to_dt=to_dt,
                    limit=page_size, offset=offset, sort_by=sort_by, order=order,
                )
                total = exporter.count(
                    project_name=project_name, project_id=project_id, user_id=user_id, session_id=session_id,
                    from_dt=from_dt, to_dt=to_dt,
                )
                return [_hydrate_trace(_strip_span_payloads(r)) for r in rows], total
            except Exception:
                self._mark_dead(exporter)
                continue
        return None

    def get_traces_for_metrics(
        self,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> List[Trace]:
        unfiltered = project_name is None and project_id is None and from_dt is None and to_dt is None
        if unfiltered:
            from_dt = datetime.now(timezone.utc) - DEFAULT_METRICS_WINDOW
        for exporter in self._queryable():
            try:
                total = exporter.count(project_name=project_name, project_id=project_id, from_dt=from_dt, to_dt=to_dt)
                if total <= 0:
                    return []
                cap = _metrics_max_traces()
                rows = exporter.query(
                    project_name=project_name, project_id=project_id,
                    from_dt=from_dt, to_dt=to_dt,
                    limit=min(total, cap), offset=0,
                )
                return [_hydrate_trace(r) for r in rows]
            except Exception:
                self._mark_dead(exporter)
                continue
        return self.get_traces()

    def get_metrics_totals(
        self,
        *,
        from_dt: datetime,
        to_dt: datetime,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Optional[dict]:
        exporter = self._readable()
        if exporter is None or self.retention_days is None or not hasattr(exporter, "query_snapshots"):
            return None

        cutoff_day = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).date()
        if from_dt.date() >= cutoff_day:
            return None

        raw_from = max(from_dt, datetime(cutoff_day.year, cutoff_day.month, cutoff_day.day, tzinfo=timezone.utc))
        daily: dict = {}
        total_traces = 0
        total_tokens_in = total_tokens_out = total_tokens_in_cached = 0
        total_cost = 0.0
        total_latency = 0

        if raw_from <= to_dt:
            raw_traces = self.get_traces_for_metrics(
                project_name=project_name, project_id=project_id, from_dt=raw_from, to_dt=to_dt,
            )
            for t in raw_traces:
                total_traces += 1
                total_tokens_in += t.total_tokens_in
                total_tokens_out += t.total_tokens_out
                total_tokens_in_cached += t.total_tokens_in_cached
                total_cost += t.cost_usd
                total_latency += t.latency_ms or 0
                day = t.started_at.strftime("%Y-%m-%d")
                d = daily.setdefault(day, {"date": day, "traces": 0, "cost_usd": 0.0})
                d["traces"] += 1
                d["cost_usd"] += t.cost_usd

        snap_to_day = min(to_dt.date(), cutoff_day - timedelta(days=1))
        if from_dt.date() <= snap_to_day:
            try:
                snaps = exporter.query_snapshots(
                    from_date=from_dt.date(), to_date=snap_to_day,
                    project_id=project_id, project_name=project_name,
                )
            except Exception:
                self._mark_dead(exporter)
                snaps = []
            for s in snaps:
                total_traces += s["trace_count"]
                total_tokens_in += s["total_tokens_in"]
                total_tokens_out += s["total_tokens_out"]
                total_tokens_in_cached += s["total_tokens_in_cached"]
                total_cost += s["total_cost_usd"]
                total_latency += s["total_latency_ms"]
                day = s["date"]
                d = daily.setdefault(day, {"date": day, "traces": 0, "cost_usd": 0.0})
                d["traces"] += s["trace_count"]
                d["cost_usd"] += s["total_cost_usd"]

        avg_latency = total_latency / total_traces if total_traces else 0
        cache_hit_rate = total_tokens_in_cached / total_tokens_in if total_tokens_in else 0.0
        return {
            "total_traces": total_traces,
            "total_cost_usd": round(total_cost, 6),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_tokens_in_cached": total_tokens_in_cached,
            "avg_latency_ms": round(avg_latency, 1),
            "cache_hit_rate": round(cache_hit_rate, 4),
            "traces_over_time": sorted(daily.values(), key=lambda d: d["date"]),
        }

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        for exporter in self._exporters:
            if not self._is_alive(exporter):
                continue
            if not callable(getattr(exporter, "get", None)):
                continue
            try:
                doc = exporter.get(trace_id)
                if doc:
                    return _hydrate_trace(doc)
            except Exception:
                self._mark_dead(exporter)
                continue
        for t in self.get_traces():
            if t.trace_id == trace_id:
                return t
        return None

    def get_sessions(
        self,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list:
        from .aggregator import compute_sessions
        traces = self.get_traces_for_metrics(project_name=project_name, project_id=project_id)
        return compute_sessions(
            traces,
            project_name=project_name,
            project_id=project_id,
            user_id=user_id,
        )

    def get_session(self, session_id: str) -> List[Trace]:
        for exporter in self._queryable():
            try:
                rows = exporter.query(session_id=session_id, limit=self._max_traces, offset=0)
                return [_hydrate_trace(r) for r in rows]
            except Exception:
                self._mark_dead(exporter)
                continue
        return [t for t in self.get_traces() if t.session_id == session_id]

    def get_projects(self) -> list:
        from .aggregator import compute_projects
        return compute_projects(self.get_traces_for_metrics())

    def get_subprojects(self, project_name: str) -> list:
        from .aggregator import compute_projects_by_id
        traces = self.get_traces_for_metrics(project_name=project_name)
        return compute_projects_by_id(traces)

    def get_project(self, project_id: str) -> List[Trace]:
        return self.get_traces_for_metrics(project_id=project_id)

    def get_filter_options(self) -> dict:
        from .aggregator import compute_filter_options
        return compute_filter_options(self.get_traces_for_metrics())

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


def _strip_span_payloads(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    spans = d.get("spans")
    if not spans:
        return d
    out = dict(d)
    stripped = []
    for s in spans:
        if not isinstance(s, dict):
            stripped.append(s)
            continue
        sc = dict(s)
        sc.pop("input", None)
        sc.pop("output", None)
        stripped.append(sc)
    out["spans"] = stripped
    return out


def _hydrate_trace(d: dict) -> Trace:
    spans = []
    for s in d.get("spans") or []:
        spans.append(Span(
            span_id=s.get("span_id", s.get("spanId", "")),
            parent_span_id=s.get("parent_span_id", s.get("parentSpanId")),
            type=SpanType(s.get("type", "llm")),
            name=s.get("name", ""),
            status=SpanStatus(s.get("status", "ok")),
            error=s.get("error"),
            started_at=_parse_dt(s.get("started_at")) or datetime.now(timezone.utc),
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

    meta = dict(d.get("metadata") or {})
    export_status = d.get("export_status") or meta.get("_export_status") or "complete"
    is_summary = bool(d.get("is_summary") if d.get("is_summary") is not None else meta.get("_is_summary"))
    export_error = d.get("export_error") if d.get("export_error") is not None else meta.get("_export_error")
    if export_status != "complete" or is_summary or export_error:
        meta["_export_status"] = export_status
        meta["_is_summary"] = is_summary or export_status == "summary_only"
        if export_error is not None:
            meta["_export_error"] = export_error

    return Trace(
        trace_id=d.get("trace_id", d.get("traceId", "")),
        name=d.get("name", "unknown"),
        started_at=_parse_dt(d.get("started_at")) or datetime.now(),
        finished_at=_parse_dt(d.get("finished_at")),
        session_id=d.get("session_id", d.get("sessionId")),
        user_id=d.get("user_id", d.get("userId")),
        project_id=d.get("project_id", d.get("projectId")),
        project_name=d.get("project_name", d.get("projectName")),
        model=d.get("model"),
        total_tokens_in=d.get("total_tokens_in", d.get("totalTokensIn", 0)),
        total_tokens_out=d.get("total_tokens_out", d.get("totalTokensOut", 0)),
        total_tokens_in_cached=d.get("total_tokens_in_cached", d.get("totalTokensInCached", 0)),
        total_tokens=d.get("total_tokens", d.get("totalTokens", 0)),
        cost_usd=d.get("cost_usd", d.get("costUsd", 0.0)),
        latency_ms=d.get("latency_ms", d.get("latencyMs")),
        tools_used=d.get("tools_used", d.get("toolsUsed", {})),
        spans=spans,
        edges=d.get("edges", []),
        metadata=meta,
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
