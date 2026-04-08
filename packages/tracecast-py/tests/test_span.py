from datetime import datetime, timezone, timedelta
from tracecast.models.span import Span, SpanType

def test_latency_ms_calculado_corretamente():
    started = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(milliseconds=250)
    span = Span(
        span_id="abc",
        type=SpanType.LLM,
        name="llm:gpt-4o",
        started_at=started,
        finished_at=finished,
    )
    assert span.latency_ms == 250

def test_latency_ms_none_sem_finished_at():
    span = Span(span_id="x", type=SpanType.TOOL, name="search", started_at=datetime.now(timezone.utc))
    assert span.latency_ms is None

def test_total_tokens_soma_in_out():
    span = Span(span_id="y", type=SpanType.LLM, name="llm:gpt-4o",
                started_at=datetime.now(timezone.utc), tokens_in=100, tokens_out=50)
    assert span.total_tokens == 150

def test_tokens_in_cached_default_zero():
    span = Span(span_id="z", type=SpanType.LLM, name="llm:gpt-4o",
                started_at=datetime.now(timezone.utc))
    assert span.tokens_in_cached == 0

def test_tokens_in_cached_aparece_no_to_dict():
    span = Span(span_id="c1", type=SpanType.LLM, name="llm:gpt-4o",
                started_at=datetime.now(timezone.utc),
                tokens_in=500, tokens_out=100, tokens_in_cached=200)
    d = span.to_dict()
    assert "tokens_in_cached" in d
    assert d["tokens_in_cached"] == 200
