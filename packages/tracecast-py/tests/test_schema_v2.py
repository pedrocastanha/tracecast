from datetime import datetime, timezone, timedelta

from tracecast.models.span import Span, SpanType, SpanStatus
from tracecast.models.trace import Trace, SCHEMA_VERSION
from tracecast.dashboard.reader import _hydrate_trace


def _span(span_id, parent, offset_ms, type=SpanType.AGENT, name=None):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Span(
        span_id=span_id,
        parent_span_id=parent,
        type=type,
        name=name or span_id,
        started_at=base + timedelta(milliseconds=offset_ms),
        finished_at=base + timedelta(milliseconds=offset_ms + 10),
    )


def test_span_parent_status_error_defaults():
    s = Span(span_id="a", type=SpanType.LLM, name="llm", started_at=datetime.now(timezone.utc))
    assert s.parent_span_id is None
    assert s.status == SpanStatus.OK
    assert s.error is None


def test_span_mark_error():
    s = Span(span_id="a", type=SpanType.TOOL, name="guard", started_at=datetime.now(timezone.utc))
    s.mark_error(ValueError("boom"))
    assert s.status == SpanStatus.ERROR
    assert s.error == "boom"
    d = s.to_dict()
    assert d["status"] == "error"
    assert d["error"] == "boom"
    assert d["parent_span_id"] is None


def test_span_to_dict_includes_parent():
    s = Span(span_id="child", parent_span_id="root", type=SpanType.LLM, name="llm",
             started_at=datetime.now(timezone.utc))
    assert s.to_dict()["parent_span_id"] == "root"


def test_trace_schema_version():
    t = Trace(trace_id="t", name="n", started_at=datetime.now(timezone.utc))
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    assert t.to_dict()["schema_version"] == SCHEMA_VERSION


def test_edges_sibling_path_ordered_by_time():
    t = Trace(trace_id="t", name="graph", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    t.spans = [
        _span("root", None, 0),
        _span("n1", "root", 10),
        _span("n3", "root", 50),
        _span("n2", "root", 30),
    ]
    t.finished_at = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    t._finalize()
    flow = [(e["from"], e["to"]) for e in t.edges if e["parent_span_id"] == "root"]
    assert flow == [("n1", "n2"), ("n2", "n3")]


def test_edges_orphan_parent_treated_as_root():
    t = Trace(trace_id="t", name="graph", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    t.spans = [
        _span("a", "missing-parent", 0),
        _span("b", "missing-parent", 10),
    ]
    t.finished_at = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    t._finalize()
    assert [(e["from"], e["to"]) for e in t.edges] == [("a", "b")]
    assert all(e["parent_span_id"] is None for e in t.edges)


def test_roundtrip_preserves_v2_fields():
    t = Trace(trace_id="t", name="graph", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    child = _span("child", "root", 10, type=SpanType.LLM, name="llm:gpt-4o")
    child.tokens_in, child.tokens_out = 100, 40
    child.mark_error("rate limit")
    t.spans = [_span("root", None, 0), child]
    t.finished_at = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    t._finalize()

    restored = _hydrate_trace(t.to_dict())
    assert {s.span_id: s.parent_span_id for s in restored.spans} == {"root": None, "child": "root"}
    err_span = next(s for s in restored.spans if s.span_id == "child")
    assert err_span.status == SpanStatus.ERROR
    assert err_span.error == "rate limit"
    assert len(restored.edges) == len(t.edges)
