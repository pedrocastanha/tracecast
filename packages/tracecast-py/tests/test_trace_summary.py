from datetime import datetime, timezone

from tracecast.core.trace_summary import build_trace_summary, EXPORT_ERROR_MAX_LEN
from tracecast.models.trace import Trace, SCHEMA_VERSION
from tracecast.models.span import Span, SpanType


def _full_trace(**overrides) -> Trace:
    started = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 7, 9, 12, 0, 1, 820000, tzinfo=timezone.utc)
    t = Trace(
        trace_id="tid-1",
        name="POST /chat",
        started_at=started,
        finished_at=finished,
        session_id="s1",
        user_id="u1",
        project_id="suporte",
        project_name="Support Bot",
        model="gpt-4o-mini",
        total_tokens_in=1200,
        total_tokens_out=340,
        total_tokens_in_cached=10,
        total_tokens=1540,
        cost_usd=0.0021,
        latency_ms=1820,
        tools_used={"search": 1},
        metadata={"k": "v"},
    )
    t.spans.append(Span(
        span_id="sp1",
        type=SpanType.LLM,
        name="llm:gpt-4o-mini",
        started_at=started,
        finished_at=finished,
        model="gpt-4o-mini",
        tokens_in=1200,
        tokens_out=340,
        input="HUGE PROMPT " * 100,
        output="HUGE OUTPUT " * 100,
    ))
    t.edges = [{"from": "a", "to": "b"}]
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def test_summary_from_trace_has_min_fields_and_empty_spans():
    t = _full_trace()
    s = build_trace_summary(t, RuntimeError("boom"))

    assert s["schema_version"] == SCHEMA_VERSION
    assert s["trace_id"] == "tid-1"
    assert s["name"] == "POST /chat"
    assert s["project_id"] == "suporte"
    assert s["project_name"] == "Support Bot"
    assert s["model"] == "gpt-4o-mini"
    assert s["session_id"] == "s1"
    assert s["user_id"] == "u1"
    assert s["total_tokens_in"] == 1200
    assert s["total_tokens_out"] == 340
    assert s["total_tokens_in_cached"] == 10
    assert s["total_tokens"] == 1540
    assert s["cost_usd"] == 0.0021
    assert s["latency_ms"] == 1820
    assert s["tools_used"] == {"search": 1}
    assert s["started_at"] == t.started_at.isoformat()
    assert s["finished_at"] == t.finished_at.isoformat()
    assert s["spans"] == []
    assert s["edges"] == []
    assert s["export_status"] == "summary_only"
    assert s["is_summary"] is True
    assert "boom" in s["export_error"]
    assert "HUGE PROMPT" not in str(s)
    assert s.get("metadata") == {}


def test_summary_from_dict_same_contract():
    t = _full_trace()
    doc = t.to_dict()
    assert doc["spans"]  # source has spans
    s = build_trace_summary(doc, "disk full")

    assert s["trace_id"] == "tid-1"
    assert s["total_tokens"] == 1540
    assert s["project_id"] == "suporte"
    assert s["name"] == "POST /chat"
    assert s["started_at"] == doc["started_at"]
    assert s["spans"] == []
    assert s["edges"] == []
    assert s["export_status"] == "summary_only"
    assert s["is_summary"] is True
    assert s["export_error"] == "disk full"


def test_export_error_truncated_to_500():
    long_err = "x" * 2000
    s = build_trace_summary(_full_trace(), long_err)
    assert len(s["export_error"]) <= EXPORT_ERROR_MAX_LEN
    assert len(s["export_error"]) == EXPORT_ERROR_MAX_LEN


def test_export_error_from_exception_uses_str():
    s = build_trace_summary(_full_trace(), ValueError("bad sink"))
    assert s["export_error"] == "bad sink"


def test_zero_tokens_still_valid_summary():
    t = _full_trace(
        total_tokens_in=0,
        total_tokens_out=0,
        total_tokens_in_cached=0,
        total_tokens=0,
        cost_usd=0.0,
        model=None,
        tools_used={},
    )
    t.spans.clear()
    t.edges.clear()
    s = build_trace_summary(t, "fail")

    assert s["trace_id"] == "tid-1"
    assert s["started_at"]
    assert s["name"] == "POST /chat"
    assert s["project_id"] == "suporte"
    assert s["total_tokens"] == 0
    assert s["total_tokens_in"] == 0
    assert s["total_tokens_out"] == 0
    assert s["export_status"] == "summary_only"
    assert s["spans"] == []


def test_missing_optional_project_fields_ok():
    t = _full_trace(project_id=None, project_name=None)
    s = build_trace_summary(t, "e")
    assert s["project_id"] is None
    assert s["project_name"] is None
    assert s["trace_id"]
    assert s["name"]
