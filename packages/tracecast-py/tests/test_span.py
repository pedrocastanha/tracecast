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
