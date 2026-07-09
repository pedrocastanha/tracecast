from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Union

from ..models.trace import SCHEMA_VERSION, Trace

EXPORT_ERROR_MAX_LEN = 500
EXPORT_STATUS_SUMMARY = "summary_only"

_SCALAR_KEYS = (
    "trace_id",
    "name",
    "session_id",
    "user_id",
    "project_id",
    "project_name",
    "model",
    "total_tokens_in",
    "total_tokens_out",
    "total_tokens_in_cached",
    "total_tokens",
    "cost_usd",
    "latency_ms",
    "tools_used",
    "started_at",
    "finished_at",
)


def _as_dict(source: Union[Trace, dict]) -> dict:
    if isinstance(source, Trace):
        return source.to_dict()
    if isinstance(source, dict):
        return source
    raise TypeError(f"build_trace_summary expected Trace or dict, got {type(source)!r}")


def _format_error(error: Union[BaseException, str]) -> str:
    if isinstance(error, BaseException):
        text = str(error) or type(error).__name__
    else:
        text = str(error)
    if len(text) <= EXPORT_ERROR_MAX_LEN:
        return text
    return text[:EXPORT_ERROR_MAX_LEN]


def _iso(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_trace_summary(
    source: Union[Trace, dict],
    error: Union[BaseException, str],
) -> Dict[str, Any]:
    raw = _as_dict(source)
    tools = raw.get("tools_used") or {}
    if not isinstance(tools, dict):
        tools = {}

    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": raw.get("trace_id") or raw.get("traceId") or "",
        "name": raw.get("name") or "unknown",
        "session_id": raw.get("session_id", raw.get("sessionId")),
        "user_id": raw.get("user_id", raw.get("userId")),
        "project_id": raw.get("project_id", raw.get("projectId")),
        "project_name": raw.get("project_name", raw.get("projectName")),
        "model": raw.get("model"),
        "total_tokens_in": int(raw.get("total_tokens_in", raw.get("totalTokensIn", 0)) or 0),
        "total_tokens_out": int(raw.get("total_tokens_out", raw.get("totalTokensOut", 0)) or 0),
        "total_tokens_in_cached": int(
            raw.get("total_tokens_in_cached", raw.get("totalTokensInCached", 0)) or 0
        ),
        "total_tokens": int(raw.get("total_tokens", raw.get("totalTokens", 0)) or 0),
        "cost_usd": float(raw.get("cost_usd", raw.get("costUsd", 0.0)) or 0.0),
        "latency_ms": raw.get("latency_ms", raw.get("latencyMs")),
        "tools_used": dict(tools),
        "spans": [],
        "edges": [],
        "metadata": {},
        "started_at": _iso(raw.get("started_at", raw.get("startedAt"))),
        "finished_at": _iso(raw.get("finished_at", raw.get("finishedAt"))),
        "export_status": EXPORT_STATUS_SUMMARY,
        "export_error": _format_error(error),
        "is_summary": True,
    }
