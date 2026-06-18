"""Shared in-memory eval filtering/sorting for file/dict exporters."""
from datetime import datetime


def _to_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (AttributeError, ValueError):
        return None


def filter_sort_evals(rows, *, project_id=None, dataset_name=None,
                      from_dt=None, to_dt=None, limit=50, offset=0):
    out = []
    for e in rows:
        if project_id and e.get("project_id") != project_id:
            continue
        if dataset_name and e.get("dataset_name") != dataset_name:
            continue
        if from_dt or to_dt:
            sd = _to_dt(e.get("started_at"))
            if from_dt and (sd is None or sd < from_dt):
                continue
            if to_dt and (sd is None or sd > to_dt):
                continue
        out.append(e)
    out.sort(key=lambda e: e.get("started_at") or "", reverse=True)
    if offset:
        out = out[offset:]
    if limit:
        out = out[:limit]
    return out


def filter_sort_scores(rows, *, trace_id=None, name=None,
                       from_dt=None, to_dt=None, limit=100, offset=0):
    out = []
    for s in rows:
        if trace_id and s.get("trace_id") != trace_id:
            continue
        if name and s.get("name") != name:
            continue
        if from_dt or to_dt:
            cd = _to_dt(s.get("created_at"))
            if from_dt and (cd is None or cd < from_dt):
                continue
            if to_dt and (cd is None or cd > to_dt):
                continue
        out.append(s)
    out.sort(key=lambda s: s.get("created_at") or "")
    if offset:
        out = out[offset:]
    if limit:
        out = out[:limit]
    return out
