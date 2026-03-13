from datetime import datetime, timezone, timedelta
from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType


def _make_span(tokens_in=100, tokens_out=50, cost=0.01, name="llm:gpt-4o", type=SpanType.LLM):
    now = datetime.now(timezone.utc)
    return Span(span_id="s1", type=type, name=name,
                started_at=now, finished_at=now + timedelta(milliseconds=100),
                tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)


def test_finalize_agrega_tokens_e_custo():
    t = Trace(trace_id="t1", name="test", started_at=datetime.now(timezone.utc))
    t.spans = [_make_span(100, 50, 0.01), _make_span(200, 80, 0.02)]
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    assert t.total_tokens_in  == 300
    assert t.total_tokens_out == 130
    assert t.total_tokens     == 430
    assert abs(t.cost_usd - 0.03) < 1e-9


def test_finalize_conta_tools_used():
    t = Trace(trace_id="t2", name="test", started_at=datetime.now(timezone.utc))
    t.spans = [
        _make_span(name="search_docs", type=SpanType.TOOL),
        _make_span(name="search_docs", type=SpanType.TOOL),
        _make_span(name="format_cv",   type=SpanType.TOOL),
    ]
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    assert t.tools_used == {"search_docs": 2, "format_cv": 1}


def test_to_dict_serializa_campos_obrigatorios():
    t = Trace(trace_id="t3", name="test", started_at=datetime.now(timezone.utc))
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    d = t.to_dict()
    assert d["trace_id"] == "t3"
    assert "spans" in d
    assert "cost_usd" in d
