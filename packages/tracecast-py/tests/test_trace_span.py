import asyncio
import pytest

from tracecast import Tracer, trace_span, trace_llm_call, set_default_tracer
from tracecast.models.span import SpanType, SpanStatus


class CapturingExporter:
    def __init__(self):
        self.records = []

    def export(self, trace):
        self.records.append(trace)

    async def aexport(self, trace):
        self.export(trace)


def test_trace_span_records_child_span():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span(name="guardrail", type=SpanType.TOOL)
    def guard(text):
        return text.upper()

    with tracer.trace("req"):
        assert guard("hi") == "HI"

    trace = exporter.records[0]
    spans = trace.spans
    assert len(spans) == 1
    assert spans[0].name == "guardrail"
    assert spans[0].type == SpanType.TOOL
    assert spans[0].input is not None
    assert spans[0].output == "HI"
    assert spans[0].latency_ms is not None


def test_trace_span_marks_error_and_reraises():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        with tracer.trace("req"):
            boom()

    span = exporter.records[0].spans[0]
    assert span.status == SpanStatus.ERROR
    assert span.error == "nope"


def test_trace_span_nests_llm_under_span():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])
    set_default_tracer(tracer)

    class FakeResp:
        usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": None})()
        choices = []

    @trace_span(name="node", type=SpanType.AGENT)
    def node():
        return trace_llm_call(lambda: FakeResp(), provider="openai", model="gpt-4o")

    with tracer.trace("req"):
        node()

    spans = {s.name: s for s in exporter.records[0].spans}
    assert "node" in spans
    llm = next(s for s in exporter.records[0].spans if s.type == SpanType.LLM)
    assert llm.parent_span_id == spans["node"].span_id


def test_trace_span_without_active_trace_is_passthrough():
    @trace_span
    def f(x):
        return x + 1

    assert f(1) == 2


def test_trace_span_async():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span(name="anode")
    async def anode(x):
        await asyncio.sleep(0)
        return x * 2

    async def run():
        async with tracer.atrace("areq"):
            return await anode(21)

    assert asyncio.run(run()) == 42
    assert exporter.records[0].spans[0].name == "anode"
    assert exporter.records[0].spans[0].output == "42"
