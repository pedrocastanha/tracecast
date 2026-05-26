import asyncio

from tracecast import Tracer, set_default_tracer, trace_cast
from tracecast.exporters.dict_exporter import DictExporter


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
