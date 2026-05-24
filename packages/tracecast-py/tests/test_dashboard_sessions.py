"""Tests for compute_sessions and compute_projects aggregator functions."""

from datetime import datetime, timezone
from tracecast.models.trace import Trace
from tracecast.dashboard.aggregator import compute_sessions, compute_projects


def _make_trace(trace_id, name, session_id=None, project_id=None, cost=0.01, tokens_in=100, tokens_out=50):
    t = Trace(
        trace_id=trace_id,
        name=name,
        started_at=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 20, 10, 1, tzinfo=timezone.utc),
        session_id=session_id,
        project_id=project_id,
        total_tokens_in=tokens_in,
        total_tokens_out=tokens_out,
        total_tokens=tokens_in + tokens_out,
        cost_usd=cost,
        latency_ms=60000,
    )
    return t


def test_compute_sessions_groups_by_session_id():
    traces = [
        _make_trace("t1", "chat1", session_id="s1", cost=0.01),
        _make_trace("t2", "chat2", session_id="s1", cost=0.02),
        _make_trace("t3", "chat3", session_id="s2", cost=0.05),
        _make_trace("t4", "chat4", session_id=None, cost=0.03),  # no session_id — skipped
    ]
    sessions = compute_sessions(traces)
    assert len(sessions) == 2
    s1 = next(s for s in sessions if s["session_id"] == "s1")
    assert s1["trace_count"] == 2
    assert abs(s1["total_cost_usd"] - 0.03) < 0.001
    assert s1["total_tokens"] == 300


def test_compute_sessions_empty():
    assert compute_sessions([]) == []


def test_compute_sessions_all_no_session():
    traces = [
        _make_trace("t1", "chat1", session_id=None),
        _make_trace("t2", "chat2", session_id=None),
    ]
    assert compute_sessions(traces) == []


def test_compute_sessions_single():
    traces = [_make_trace("t1", "chat1", session_id="s1", cost=0.05, tokens_in=200, tokens_out=100)]
    sessions = compute_sessions(traces)
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s1"
    assert sessions[0]["trace_count"] == 1
    assert sessions[0]["total_cost_usd"] == 0.05
    assert sessions[0]["total_tokens"] == 300
    assert sessions[0]["total_tokens_in"] == 200
    assert sessions[0]["total_tokens_out"] == 100
    assert "first_trace_at" in sessions[0]
    assert "last_trace_at" in sessions[0]


def test_compute_sessions_sorted_by_last_trace_desc():
    from datetime import timedelta
    t1 = Trace(
        trace_id="t1", name="a",
        started_at=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        session_id="s_old",
        total_tokens_in=0, total_tokens_out=0, total_tokens=0,
        cost_usd=0.0,
    )
    t2 = Trace(
        trace_id="t2", name="b",
        started_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
        session_id="s_new",
        total_tokens_in=0, total_tokens_out=0, total_tokens=0,
        cost_usd=0.0,
    )
    sessions = compute_sessions([t1, t2])
    assert sessions[0]["session_id"] == "s_new"
    assert sessions[1]["session_id"] == "s_old"


def test_compute_projects_groups_by_project_id():
    traces = [
        _make_trace("t1", "chat1", project_id="p1", cost=0.01),
        _make_trace("t2", "chat2", project_id="p1", cost=0.02),
        _make_trace("t3", "chat3", project_id="p2", cost=0.05),
    ]
    projects = compute_projects(traces)
    assert len(projects) == 2
    p1 = next(p for p in projects if p["project_id"] == "p1")
    assert p1["trace_count"] == 2
    assert abs(p1["total_cost_usd"] - 0.03) < 0.001


def test_compute_projects_skips_no_project():
    traces = [
        _make_trace("t1", "chat1", project_id="p1", cost=0.01),
        _make_trace("t2", "chat2", project_id=None, cost=0.99),
    ]
    projects = compute_projects(traces)
    assert len(projects) == 1
    assert projects[0]["project_id"] == "p1"


def test_compute_projects_empty():
    assert compute_projects([]) == []


def test_compute_projects_fields():
    traces = [_make_trace("t1", "chat1", project_id="p1", cost=0.1, tokens_in=500, tokens_out=250)]
    projects = compute_projects(traces)
    assert len(projects) == 1
    p = projects[0]
    assert p["project_id"] == "p1"
    assert p["trace_count"] == 1
    assert p["total_cost_usd"] == 0.1
    assert p["total_tokens"] == 750
    assert p["total_tokens_in"] == 500
    assert p["total_tokens_out"] == 250
    assert "first_trace_at" in p
    assert "last_trace_at" in p
