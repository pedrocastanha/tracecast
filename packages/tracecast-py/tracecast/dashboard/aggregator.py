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
    models_breakdown: dict[str, dict] = defaultdict(lambda: {"calls": 0, "total_tokens": 0, "total_tokens_in": 0, "total_tokens_out": 0, "cost_usd": 0.0})
    for t in filtered:
        if t.project_id:
            cost_by_project[t.project_id] += t.cost_usd
        for s in t.spans:
            if s.type.value == "llm" and s.model:
                cost_by_model[s.model] += s.cost_usd
                models_breakdown[s.model]["calls"] += 1
                models_breakdown[s.model]["total_tokens"] += s.total_tokens
                models_breakdown[s.model]["total_tokens_in"] += s.tokens_in
                models_breakdown[s.model]["total_tokens_out"] += s.tokens_out
                models_breakdown[s.model]["cost_usd"] = round(
                    models_breakdown[s.model]["cost_usd"] + s.cost_usd, 6
                )

    traces_over_time = _group_by_day(filtered)
    tokens_by_model_over_time = _group_by_day_and_model(filtered)

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
        "models_breakdown": {k: v for k, v in sorted(models_breakdown.items())},
        "traces_over_time": traces_over_time,
        "tokens_by_model_over_time": tokens_by_model_over_time,
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
        "project_name": trace.project_name,
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
    # T5: exclude broken orphan LLM spans (pid=None + 0 tokens = wrap_openai async bug).
    # Temporary until wrap_openai async fix lands in tracecast lib.
    valid_spans = [
        s for s in trace.spans
        if not (
            s.parent_span_id is None
            and s.type.value == "llm"
            and s.tokens_in == 0
            and s.tokens_out == 0
        )
    ]

    span_by_id = {s.span_id: s for s in valid_spans}
    valid_ids = set(span_by_id.keys())

    # Build parent→children map
    children: dict[str, list] = defaultdict(list)
    for s in valid_spans:
        if s.parent_span_id and s.parent_span_id in span_by_id:
            children[s.parent_span_id].append(s.span_id)

    # Aggregate tokens + primary_model bottom-up (DFS, memoized).
    # primary_model = model of the LLM descendant with most tokens (for parent card display).
    agg_cache: dict[str, tuple] = {}

    def _agg(sid: str) -> tuple:
        if sid in agg_cache:
            return agg_cache[sid]
        s = span_by_id[sid]
        ti, to_, cost = s.tokens_in, s.tokens_out, s.cost_usd
        primary_model: str | None = s.model if s.type.value == "llm" else None
        best_child_tok = 0
        for child_id in children.get(sid, []):
            ci, co, cc, cm = _agg(child_id)
            ti += ci
            to_ += co
            cost += cc
            child_tok = ci + co
            if cm is not None and child_tok > best_child_tok:
                primary_model = cm
                best_child_tok = child_tok
        agg_cache[sid] = (ti, to_, cost, primary_model)
        return ti, to_, cost, primary_model

    nodes = []
    for s in valid_spans:
        ti, to_, cost, pm = _agg(s.span_id)
        nodes.append({
            "id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "type": s.type.value,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "model": s.model,
            "primary_model": pm,
            "tokens_in": ti,
            "tokens_out": to_,
            "total_tokens": ti + to_,
            "cost_usd": round(cost, 6),
            "latency_ms": s.latency_ms,
            "error": s.error,
        })

    # Filter edges to only reference valid span ids (removes orphan edges)
    valid_edges = [
        e for e in trace.edges
        if e.get("from") in valid_ids and e.get("to") in valid_ids
    ]

    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "nodes": nodes,
        "edges": valid_edges,
    }


def compute_sessions(
    traces: List[Trace],
    *,
    project_name: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list:
    """Aggregate traces by session_id with optional hierarchical filtering."""
    filtered = traces
    if project_name:
        filtered = [t for t in filtered if t.project_name == project_name]
    if project_id:
        filtered = [t for t in filtered if t.project_id == project_id]
    if user_id:
        filtered = [t for t in filtered if t.user_id == user_id]

    groups: dict[str, dict] = {}
    for t in filtered:
        sid = t.session_id
        if not sid:
            continue
        if sid not in groups:
            groups[sid] = {
                "session_id": sid,
                "project_name": t.project_name,
                "project_id": t.project_id,
                "user_id": t.user_id,
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
    """Group by project_name if available; fall back to project_id."""
    use_name = any(t.project_name for t in traces)
    groups: dict[str, dict] = {}
    for t in traces:
        key = t.project_name if use_name else t.project_id
        if not key:
            continue
        if key not in groups:
            groups[key] = {
                "project_name" if use_name else "project_id": key,
                "trace_count": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "_first_dt": t.started_at,
                "_last_dt": t.started_at,
            }
        g = groups[key]
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


def compute_projects_by_id(traces: List[Trace]) -> list:
    """Aggregate traces by project_id (filial level, used for drill-down under a project_name)."""
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


def compute_filter_options(traces: List[Trace]) -> dict:
    """Return available values for cascading filter dropdowns: project_name → project_id → user_id."""
    project_names = sorted({t.project_name for t in traces if t.project_name})
    by_name: dict[str, set] = defaultdict(set)
    by_pid: dict[str, set] = defaultdict(set)
    for t in traces:
        if t.project_name and t.project_id:
            by_name[t.project_name].add(t.project_id)
        if t.project_id and t.user_id:
            by_pid[t.project_id].add(t.user_id)
    return {
        "project_names": project_names,
        "project_ids": {k: sorted(v) for k, v in by_name.items()},
        "user_ids": {k: sorted(v) for k, v in by_pid.items()},
    }


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


def _group_by_day_and_model(traces: List[Trace]) -> list:
    """Group by (date, model) at span level for multi-series token/cost chart."""
    groups: dict[tuple, dict] = {}
    for t in traces:
        day = t.started_at.strftime("%Y-%m-%d")
        for s in t.spans:
            if s.type.value != "llm" or not s.model:
                continue
            model = s.model
            key = (day, model)
            if key not in groups:
                groups[key] = {"date": day, "model": model, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
            groups[key]["tokens_in"] += s.tokens_in
            groups[key]["tokens_out"] += s.tokens_out
            groups[key]["cost_usd"] = round(groups[key]["cost_usd"] + s.cost_usd, 6)
    return sorted(groups.values(), key=lambda x: (x["date"], x["model"]))
