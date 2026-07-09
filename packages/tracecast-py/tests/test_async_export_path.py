import asyncio
import time
from unittest.mock import MagicMock

from tracecast.core.tracer import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def test_atrace_background_returns_before_slow_export():
    gate = {"closed": True}
    exported = []

    class SlowExporter(DictExporter):
        def export_docs_batch(self, docs):
            while gate["closed"]:
                time.sleep(0.01)
            super().export_docs_batch(docs)
            exported.extend(docs)

    exp = SlowExporter()
    tracer = Tracer(
        exporters=[exp],
        background_export=True,
        flush_at=1,
        flush_interval=0.05,
        export_queue_size=10,
    )

    async def run():
        t0 = time.monotonic()
        async with tracer.atrace("async-agent", project_id="p1"):
            await asyncio.sleep(0.01)
        elapsed = time.monotonic() - t0
        return elapsed

    elapsed = asyncio.run(run())
    assert elapsed < 0.5, f"atrace blocked on export: {elapsed:.3f}s"
    gate["closed"] = False
    assert tracer.flush(timeout=2.0)
    assert len(exported) == 1
    assert exported[0]["name"] == "async-agent"


def test_atrace_to_dict_offloaded_still_exports():
    exp = DictExporter()
    tracer = Tracer(
        exporters=[exp],
        background_export=True,
        flush_at=1,
        flush_interval=0.05,
    )

    async def run():
        async with tracer.atrace("fast"):
            pass
        await tracer.aflush(timeout=2.0)

    asyncio.run(run())
    assert len(exp.traces) == 1


def test_atrace_without_background_schedules_task():
    done = asyncio.Event()
    hits = {"n": 0}

    class Asyncish(DictExporter):
        async def aexport(self, trace):
            hits["n"] += 1
            await asyncio.sleep(0.05)
            super().export(trace)
            done.set()

    exp = Asyncish()
    tracer = Tracer(exporters=[exp], background_export=False, blocking_export=False)

    async def run():
        t0 = time.monotonic()
        async with tracer.atrace("scheduled"):
            pass
        elapsed = time.monotonic() - t0
        assert elapsed < 0.04, f"should not await export: {elapsed:.3f}s"
        await asyncio.wait_for(done.wait(), timeout=2.0)
        assert hits["n"] == 1
        assert len(exp.traces) == 1

    asyncio.run(run())
