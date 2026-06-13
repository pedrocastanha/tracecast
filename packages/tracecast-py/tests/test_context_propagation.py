import asyncio
from concurrent.futures import ThreadPoolExecutor

from tracecast import Tracer, trace_span, bind_context
from tracecast.models.span import SpanType


class CapturingExporter:
    def __init__(self):
        self.records = []

    def export(self, trace):
        self.records.append(trace)

    async def aexport(self, trace):
        self.export(trace)


def test_thread_without_bind_loses_trace():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span(name="node")
    def node():
        return Tracer.current() is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        with tracer.trace("req"):
            seen = pool.submit(node).result()

    assert seen is False
    assert len(exporter.records[0].spans) == 0


def test_bind_context_propagates_trace_to_thread():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span(name="node", type=SpanType.AGENT)
    def node():
        assert Tracer.current() is not None
        return "ok"

    with ThreadPoolExecutor(max_workers=4) as pool:
        with tracer.trace("req"):
            futures = [pool.submit(bind_context(node)) for _ in range(5)]
            results = [f.result() for f in futures]

    assert results == ["ok"] * 5
    assert len(exporter.records[0].spans) == 5
    assert all(s.name == "node" for s in exporter.records[0].spans)


def test_bind_context_propagates_in_run_in_executor():
    exporter = CapturingExporter()
    tracer = Tracer(exporters=[exporter])

    @trace_span(name="blocking")
    def blocking(x):
        return x * 10

    async def run():
        async with tracer.atrace("req"):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, bind_context(blocking, 4))

    assert asyncio.run(run()) == 40
    assert exporter.records[0].spans[0].name == "blocking"
