import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType
from tracecast.instrumentors._streaming import stream_openai, stream_anthropic


def _span():
    return Span(span_id="s", type=SpanType.LLM, name="llm:gpt-4o", model="gpt-4o",
                started_at=datetime.now(timezone.utc))


def _trace():
    return Trace(trace_id="t", name="r", started_at=datetime.now(timezone.utc))


def _openai_chunks():
    return [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"))], usage=None),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))], usage=None),
        SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=1)),
        ),
    ]


def test_stream_openai_accumulates_tokens_and_output():
    span, trace = _span(), _trace()
    consumed = list(stream_openai(iter(_openai_chunks()), span, trace, "gpt-4o"))
    assert len(consumed) == 3
    assert len(trace.spans) == 1
    s = trace.spans[0]
    assert s.tokens_in == 10
    assert s.tokens_out == 2
    assert s.tokens_in_cached == 1
    assert s.output == "Hello"
    assert s.cost_usd > 0
    assert s.finished_at is not None


def test_stream_anthropic_accumulates():
    events = [
        SimpleNamespace(type="message_start", message=SimpleNamespace(
            usage=SimpleNamespace(input_tokens=8, cache_read_input_tokens=0))),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="Hi ")),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="there")),
        SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=4)),
    ]
    span, trace = _span(), _trace()
    list(stream_anthropic(iter(events), span, trace, "claude-sonnet-4-6"))
    s = trace.spans[0]
    assert s.tokens_in == 8
    assert s.tokens_out == 4
    assert s.output == "Hi there"


def test_stream_span_finalizes_even_if_partial_consumption():
    span, trace = _span(), _trace()
    gen = stream_openai(iter(_openai_chunks()), span, trace, "gpt-4o")
    next(gen)
    gen.close()
    assert len(trace.spans) == 1


def _make_fake_openai_stream():
    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    chat = types.ModuleType("openai.resources.chat")
    completions_mod = types.ModuleType("openai.resources.chat.completions")

    class Completions:
        def create(self, **kwargs):
            assert kwargs.get("stream") is True
            assert kwargs.get("stream_options") == {"include_usage": True}
            return iter(_openai_chunks())

    completions_mod.Completions = Completions
    chat.completions = completions_mod
    resources.chat = chat
    openai.resources = resources
    for name, mod in [
        ("openai", openai), ("openai.resources", resources),
        ("openai.resources.chat", chat), ("openai.resources.chat.completions", completions_mod),
    ]:
        sys.modules[name] = mod
    return Completions


def test_openai_instrumentor_streaming_integration():
    Completions = _make_fake_openai_stream()
    try:
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()
        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = Completions()

        with tracer.trace("stream-test"):
            stream = client.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True)
            chunks = list(stream)

        assert len(chunks) == 3
        span = exporter.traces[0]["spans"][0]
        assert span["tokens_in"] == 10
        assert span["tokens_out"] == 2
        assert span["output"] == "Hello"
        inst.unpatch()
    finally:
        for k in list(sys.modules):
            if k.startswith("openai"):
                del sys.modules[k]
