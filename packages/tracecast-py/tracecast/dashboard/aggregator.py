"""Pure functions for computing dashboard metrics from a list of traces. No I/O, no state."""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from ..models.trace import Trace


def compute_metrics(
    traces: List[Trace],
    *,
    period: str = "7d",
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    project_id: Optional[str] = None,
) -> dict:
    if from_dt is None:
        now = datetime.now(timezone.utc)
        delta = _period_delta(period)
        from_dt = now - delta
        to_dt = now

    filtered = traces
    if project_id:
        filtered = [t for t in filtered if t.project_id == project_id]
    filtered = [
        t for t in filtered
        if from_dt <= t.started_at <= (to_dt or datetime.now(timezone.utc))
    ]

    total_traces = len(filtered)
    total_cost = sum(t.cost_usd for t in filtered)
    total_tokens_in = sum(t.total_tokens_in for t in filtered)
    total_tokens_out = sum(t.total_tokens_out for t in filtered)
    total_tokens_cached = sum(t.total_tokens_in_cached for t in filtered)
    avg_latency = (
        sum(t.latency_ms or 0 for t in filtered) / total_traces
        if total_traces > 0 else 0
    )
    cache_hit_rate = (
        total_tokens_cached / total_tokens_in if total_tokens_in > 0 else 0.0
    )

    cost_by_model: dict[str, float] = defaultdict(float)
    cost_by_project: dict[str, float] = defaultdict(float)
    for t in filtered:
        if t.model:
            cost_by_model[t.model] += t.cost_usd
        if t.project_id:
            cost_by_project[t.project_id] += t.cost_usd

    traces_over_time = _group_by_day(filtered)

    return {
        "period": period,
        "total_traces": total_traces,
        "total_cost_usd": round(total_cost, 6),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_tokens_in_cached": total_tokens_cached,
        "cache_hit_rate": round(cache_hit_rate, 4),
        "avg_latency_ms": round(avg_latency, 1),
        "cost_by_model": dict(cost_by_model),
        "cost_by_project": dict(cost_by_project),
        "traces_over_time": traces_over_time,
    }


def paginate_traces(
    traces: List[Trace],
    *,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "date",
    order: str = "desc",
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> dict:
    filtered = traces
    if project_id:
        filtered = [t for t in filtered if t.project_id == project_id]
    if user_id:
        filtered = [t for t in filtered if t.user_id == user_id]
    if from_dt:
        filtered = [t for t in filtered if t.started_at >= from_dt]
    if to_dt:
        filtered = [t for t in filtered if t.started_at <= to_dt]

    key_map = {
        "cost": lambda t: t.cost_usd,
        "duration": lambda t: t.latency_ms or 0,
        "tokens": lambda t: t.total_tokens,
        "date": lambda t: t.started_at,
    }
    key = key_map.get(sort_by, key_map["date"])
    reverse = order == "desc"
    filtered.sort(key=key, reverse=reverse)

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]

    return {
        "traces": [_trace_summary(t) for t in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _trace_summary(trace: Trace) -> dict:
    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "project_id": trace.project_id,
        "user_id": trace.user_id,
        "session_id": trace.session_id,
        "model": trace.model,
        "started_at": trace.started_at.isoformat(),
        "finished_at": trace.finished_at.isoformat() if trace.finished_at else None,
        "latency_ms": trace.latency_ms,
        "total_tokens_in": trace.total_tokens_in,
        "total_tokens_out": trace.total_tokens_out,
        "total_tokens_in_cached": trace.total_tokens_in_cached,
        "total_tokens": trace.total_tokens,
        "cost_usd": trace.cost_usd,
        "span_count": len(trace.spans),
        "tools_used": trace.tools_used,
    }


def build_graph(trace: Trace) -> dict:
    nodes = []
    for s in trace.spans:
        nodes.append({
            "id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "type": s.type.value,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "model": s.model,
            "tokens_in": s.tokens_in,
            "tokens_out": s.tokens_out,
            "total_tokens": s.total_tokens,
            "cost_usd": s.cost_usd,
            "latency_ms": s.latency_ms,
            "error": s.error,
        })
    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "nodes": nodes,
        "edges": trace.edges,
    }


def compute_sessions(traces: List[Trace]) -> list:
    """Aggregate traces by session_id. Traces without session_id are skipped."""
    groups: dict[str, dict] = {}
    for t in traces:
        sid = t.session_id
        if not sid:
            continue
        if sid not in groups:
            groups[sid] = {
                "session_id": sid,
                "trace_count": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "_first_dt": t.started_at,
                "_last_dt": t.started_at,
            }
        g = groups[sid]
        g["trace_count"] += 1
        g["total_cost_usd"] += t.cost_usd
        g["total_tokens"] += t.total_tokens
        g["total_tokens_in"] += t.total_tokens_in
        g["total_tokens_out"] += t.total_tokens_out
        dt = t.started_at
        if dt < g["_first_dt"]:
            g["_first_dt"] = dt
        if dt > g["_last_dt"]:
            g["_last_dt"] = dt
    result = sorted(groups.values(), key=lambda x: x["_last_dt"], reverse=True)
    for r in result:
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
        r["first_trace_at"] = r.pop("_first_dt").isoformat()
        r["last_trace_at"] = r.pop("_last_dt").isoformat()
    return result


def compute_projects(traces: List[Trace]) -> list:
    """Aggregate traces by project_id. Traces without project_id are skipped."""
    groups: dict[str, dict] = {}
    for t in traces:
        pid = t.project_id
        if not pid:
            continue
        if pid not in groups:
            groups[pid] = {
                "project_id": pid,
                "trace_count": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "_first_dt": t.started_at,
                "_last_dt": t.started_at,
            }
        g = groups[pid]
        g["trace_count"] += 1
        g["total_cost_usd"] += t.cost_usd
        g["total_tokens"] += t.total_tokens
        g["total_tokens_in"] += t.total_tokens_in
        g["total_tokens_out"] += t.total_tokens_out
        dt = t.started_at
        if dt < g["_first_dt"]:
            g["_first_dt"] = dt
        if dt > g["_last_dt"]:
            g["_last_dt"] = dt
    result = sorted(groups.values(), key=lambda x: x["_last_dt"], reverse=True)
    for r in result:
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
        r["first_trace_at"] = r.pop("_first_dt").isoformat()
        r["last_trace_at"] = r.pop("_last_dt").isoformat()
    return result


def _period_delta(period: str) -> timedelta:
    mapping = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    return mapping.get(period, timedelta(days=7))


def _group_by_day(traces: List[Trace]) -> list:
    groups: dict[str, dict] = defaultdict(lambda: {"date": "", "traces": 0, "cost_usd": 0.0})
    for t in traces:
        day = t.started_at.strftime("%Y-%m-%d")
        groups[day]["date"] = day
        groups[day]["traces"] += 1
        groups[day]["cost_usd"] += t.cost_usd
    return sorted(groups.values(), key=lambda x: x["date"])
