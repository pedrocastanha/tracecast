"""Pure functions for computing dashboard metrics from a list of traces. No I/O, no state."""

import ast
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from ..models.trace import Trace

HIDDEN_CHAIN_NAMES = {
    "LangGraph", "RunnableSequence", "Prompt", "ChatPromptTemplate",
    "call_model", "should_continue", "agent", "tools",
}


def compute_metrics(
    traces: List[Trace],
    *,
    period: str = "7d",
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    project_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    if from_dt is None:
        now = datetime.now(timezone.utc)
        delta = _period_delta(period)
        from_dt = now - delta
        to_dt = now

    filtered = traces
    if project_name:
        filtered = [t for t in filtered if t.project_name == project_name]
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
    project_name: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> dict:
    filtered = traces
    if project_name:
        filtered = [t for t in filtered if t.project_name == project_name]
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


def _short_name(name: str) -> str:
    return name.split(":")[-1] if name else name


def _parse_tool_params(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            value = loader(raw)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _is_curated(span) -> bool:
    return bool(getattr(span, "metadata", None) and span.metadata.get("tc_display"))


def _llm_call(c) -> dict:
    return {
        "model": c.model,
        "tokens_in": c.tokens_in,
        "tokens_out": c.tokens_out,
        "cost_usd": round(c.cost_usd, 6),
        "input": c.input,
        "output": c.output,
    }


def _node_from_calls(s, calls: list) -> dict:
    calls = sorted(calls, key=lambda c: c.started_at)
    own_in = sum(c.tokens_in for c in calls)
    own_out = sum(c.tokens_out for c in calls)
    own_cost = sum(c.cost_usd for c in calls)
    primary_model = max(calls, key=lambda c: c.total_tokens).model if calls else None
    return {
        "id": s.span_id,
        "parent_span_id": s.parent_span_id,
        "name": s.name,
        "type": s.type.value,
        "status": s.status.value if hasattr(s.status, "value") else s.status,
        "model": s.model,
        "primary_model": primary_model,
        "own_tokens_in": own_in,
        "own_tokens_out": own_out,
        "own_total_tokens": own_in + own_out,
        "own_cost_usd": round(own_cost, 6),
        "llm_calls": [_llm_call(c) for c in calls],
        "tool_params": _parse_tool_params(s.input) if s.type.value == "tool" else None,
        "latency_ms": s.latency_ms,
        "error": s.error,
    }


def build_graph(trace: Trace) -> dict:
    valid_spans = [
        s for s in trace.spans
        if not (
            s.parent_span_id is None
            and s.type.value == "llm"
            and s.tokens_in == 0
            and s.tokens_out == 0
        )
    ]

    curated = [s for s in valid_spans if _is_curated(s)]
    if curated:
        return _build_graph_curated(trace, valid_spans, curated)

    span_by_id = {s.span_id: s for s in valid_spans}

    def _nearest_visible(sid: Optional[str]) -> Optional[str]:
        seen: set = set()
        current = span_by_id.get(sid) if sid else None
        while current is not None and current.span_id not in seen:
            seen.add(current.span_id)
            current = span_by_id.get(current.parent_span_id)
            if current is None:
                return None
            if current.type.value != "llm" and _short_name(current.name) not in HIDDEN_CHAIN_NAMES:
                return current.span_id
        return None

    def _nearest_any(sid: Optional[str]) -> Optional[str]:
        seen: set = set()
        current = span_by_id.get(sid) if sid else None
        while current is not None and current.span_id not in seen:
            seen.add(current.span_id)
            current = span_by_id.get(current.parent_span_id)
            if current is None:
                return None
            if current.type.value != "llm":
                return current.span_id
        return None

    attributed: dict[str, list] = defaultdict(list)
    total_in = total_out = 0
    total_cost = 0.0
    for s in valid_spans:
        if s.type.value != "llm":
            continue
        total_in += s.tokens_in
        total_out += s.tokens_out
        total_cost += s.cost_usd
        target = _nearest_visible(s.span_id) or _nearest_any(s.span_id)
        if target is not None:
            attributed[target].append(s)

    nodes = []
    for s in valid_spans:
        if s.type.value == "llm":
            continue
        calls = sorted(attributed.get(s.span_id, []), key=lambda c: c.started_at)
        own_in = sum(c.tokens_in for c in calls)
        own_out = sum(c.tokens_out for c in calls)
        own_cost = sum(c.cost_usd for c in calls)
        primary_model = None
        if calls:
            primary_model = max(calls, key=lambda c: c.total_tokens).model
        llm_calls = [
            {
                "model": c.model,
                "tokens_in": c.tokens_in,
                "tokens_out": c.tokens_out,
                "cost_usd": round(c.cost_usd, 6),
                "input": c.input,
                "output": c.output,
            }
            for c in calls
        ]
        tool_params = _parse_tool_params(s.input) if s.type.value == "tool" else None
        nodes.append({
            "id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "type": s.type.value,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "model": s.model,
            "primary_model": primary_model,
            "own_tokens_in": own_in,
            "own_tokens_out": own_out,
            "own_total_tokens": own_in + own_out,
            "own_cost_usd": round(own_cost, 6),
            "llm_calls": llm_calls,
            "tool_params": tool_params,
            "latency_ms": s.latency_ms,
            "error": s.error,
        })

    node_ids = {n["id"] for n in nodes}
    valid_edges = [
        e for e in trace.edges
        if e.get("from") in node_ids and e.get("to") in node_ids
    ]

    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "nodes": nodes,
        "edges": valid_edges,
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "total_tokens": total_in + total_out,
        "cost_usd": round(total_cost, 6),
    }


def _build_graph_curated(trace: Trace, valid_spans: list, curated: list) -> dict:
    def _end(s):
        return s.finished_at or s.started_at

    def _containers(point, exclude=None):
        return [
            c for c in curated
            if c.span_id != exclude and c.started_at <= point <= _end(c)
        ]

    attributed: dict[str, list] = defaultdict(list)
    total_in = total_out = 0
    total_cost = 0.0
    for s in valid_spans:
        if s.type.value != "llm":
            continue
        total_in += s.tokens_in
        total_out += s.tokens_out
        total_cost += s.cost_usd
        containers = _containers(s.started_at)
        if containers:
            target = max(containers, key=lambda c: c.started_at)
            attributed[target.span_id].append(s)

    def _sort_key(c):
        order = c.metadata.get("tc_order")
        if order is not None:
            return (0, order, c.started_at)
        return (1, c.started_at, c.started_at)

    ordered = sorted(curated, key=_sort_key)

    def _parent_of(c):
        containers = _containers(c.started_at, exclude=c.span_id)
        if not containers:
            return None
        return max(containers, key=lambda x: x.started_at).span_id

    parent_by_id = {c.span_id: _parent_of(c) for c in curated}

    nodes = []
    for c in ordered:
        node = _node_from_calls(c, attributed.get(c.span_id, []))
        node["parent_span_id"] = parent_by_id[c.span_id]
        nodes.append(node)

    children: dict = defaultdict(list)
    for c in ordered:
        children[parent_by_id[c.span_id]].append(c.span_id)

    edges = []
    for parent, kids in children.items():
        for prev, cur in zip(kids, kids[1:]):
            edges.append({"from": prev, "to": cur, "conditional": False})
        if parent is not None and kids:
            edges.append({"from": parent, "to": kids[0], "conditional": False})

    # Add tool spans as nodes with dashed edges from their parent curated agent.
    curated_ids = {c.span_id for c in curated}
    span_by_id = {s.span_id: s for s in valid_spans}
    tool_spans = sorted(
        [s for s in valid_spans if s.type.value == "tool" and s.span_id not in curated_ids],
        key=lambda s: s.started_at,
    )

    tools_by_parent: dict = defaultdict(list)
    for t in tool_spans:
        # Walk up to nearest curated ancestor.
        pid = t.parent_span_id
        while pid and pid not in curated_ids:
            ancestor = span_by_id.get(pid)
            pid = ancestor.parent_span_id if ancestor else None
        # Aggregate LLM calls whose parent_span_id is this tool.
        tool_llms = sorted(
            [s for s in valid_spans if s.type.value == "llm" and s.parent_span_id == t.span_id],
            key=lambda s: s.started_at,
        )
        own_in = sum(c.tokens_in for c in tool_llms)
        own_out = sum(c.tokens_out for c in tool_llms)
        own_cost = sum(c.cost_usd for c in tool_llms)
        primary_model = max(tool_llms, key=lambda c: c.total_tokens).model if tool_llms else None
        nodes.append({
            "id": t.span_id,
            "parent_span_id": pid,
            "name": t.name,
            "type": "tool",
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "model": primary_model,
            "primary_model": primary_model,
            "own_tokens_in": own_in,
            "own_tokens_out": own_out,
            "own_total_tokens": own_in + own_out,
            "own_cost_usd": round(own_cost, 6),
            "llm_calls": [
                {
                    "model": c.model,
                    "tokens_in": c.tokens_in,
                    "tokens_out": c.tokens_out,
                    "cost_usd": round(c.cost_usd, 6),
                    "input": c.input,
                    "output": c.output,
                }
                for c in tool_llms
            ],
            "tool_params": _parse_tool_params(t.input),
            "latency_ms": t.latency_ms,
            "error": t.error,
        })
        if pid:
            tools_by_parent[pid].append(t.span_id)

    # Dashed edges: agent → tool1 → tool2 → ... → agent (return)
    for parent_id, tool_ids in tools_by_parent.items():
        edges.append({"from": parent_id, "to": tool_ids[0], "conditional": True})
        for prev, cur in zip(tool_ids, tool_ids[1:]):
            edges.append({"from": prev, "to": cur, "conditional": True})
        edges.append({"from": tool_ids[-1], "to": parent_id, "conditional": True})

    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "nodes": nodes,
        "edges": edges,
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "total_tokens": total_in + total_out,
        "cost_usd": round(total_cost, 6),
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
