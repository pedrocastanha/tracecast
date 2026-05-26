import asyncio
from types import SimpleNamespace

from tracecast import Tracer, set_default_tracer, trace_cast, wrap_openai
from tracecast.exporters.dict_exporter import DictExporter


class FakeCompletions:
    def create(self, **kwargs):
        usage = SimpleNamespace(
            prompt_tokens=90,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        )
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(usage=usage, choices=[choice], model=kwargs["model"])


class FakeOpenAI:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_trace_cast_uses_default_tracer_configured_after_decoration(monkeypatch):
    import tracecast.decorators as decorators

    monkeypatch.setattr(decorators, "_default_tracer", None)
    exporter = DictExporter()

    @trace_cast
    def route_handler():
        return "ok"

    set_default_tracer(Tracer(exporters=[exporter]))

    assert route_handler() == "ok"
    assert len(exporter.traces) == 1
    assert exporter.traces[0]["name"].endswith("route_handler")


def test_trace_cast_async_uses_default_tracer_configured_after_decoration(monkeypatch):
    import tracecast.decorators as decorators

    monkeypatch.setattr(decorators, "_default_tracer", None)
    exporter = DictExporter()

    @trace_cast(name="async-route")
    async def route_handler():
        return "ok"

    set_default_tracer(Tracer(exporters=[exporter]))

    assert asyncio.run(route_handler()) == "ok"
    assert len(exporter.traces) == 1
    assert exporter.traces[0]["name"] == "async-route"


def test_trace_cast_is_primary_flow_for_wrapped_llm_tokens(monkeypatch):
    import tracecast.decorators as decorators

    monkeypatch.setattr(decorators, "_default_tracer", None)
    exporter = DictExporter()
    client = wrap_openai(FakeOpenAI())

    @trace_cast(name="decorated-llm-route", project_id="decorator-main")
    def route_handler():
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
        )
        return "ok"

    set_default_tracer(Tracer(exporters=[exporter]))

    assert route_handler() == "ok"
    trace = exporter.traces[0]

    assert trace["name"] == "decorated-llm-route"
    assert trace["project_id"] == "decorator-main"
    assert trace["total_tokens_in"] == 90
    assert trace["total_tokens_out"] == 30
    assert trace["total_tokens_in_cached"] == 20
    assert trace["total_tokens"] == 120
    assert trace["spans"][0]["model"] == "gpt-4o"
