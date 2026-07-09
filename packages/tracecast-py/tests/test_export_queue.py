import logging
import threading
import time
from unittest.mock import MagicMock

from tracecast.core.tracer import Tracer
from tracecast.core.export_queue import ExportWorker
from tracecast.core.payload import truncate_payload, max_payload_chars
from tracecast.exporters.dict_exporter import DictExporter


def test_background_export_offloads_and_flush():
    exporter = DictExporter()
    tracer = Tracer(
        exporters=[exporter],
        background_export=True,
        export_queue_size=50,
        flush_at=1,
        flush_interval=0.05,
    )
    with tracer.trace("bg"):
        pass
    assert tracer.flush(timeout=2.0) is True
    assert len(exporter.traces) == 1


def test_background_export_async_uses_queue_not_unbounded_tasks():
    exporter = DictExporter()
    tracer = Tracer(
        exporters=[exporter],
        background_export=True,
        export_queue_size=20,
        flush_at=1,
        flush_interval=0.05,
    )

    async def run():
        async with tracer.atrace("async-bg"):
            pass
        await tracer.aflush(timeout=2.0)

    import asyncio
    asyncio.run(run())
    assert len(exporter.traces) == 1


def test_background_export_error_surfaced_after_flush(caplog):
    bad = MagicMock()
    bad.export_docs_batch.side_effect = IOError("disk full")
    tracer = Tracer(
        exporters=[bad],
        background_export=True,
        export_queue_size=10,
        flush_at=1,
        flush_interval=0.05,
    )

    with caplog.at_level(logging.WARNING, logger="tracecast"):
        with tracer.trace("fail-bg"):
            pass
        assert tracer.flush(timeout=2.0) is True

    assert any("disk full" in r.getMessage() for r in caplog.records)


def test_export_queue_drops_when_full(caplog):
    gate = threading.Event()
    exported = []

    def slow_batch(docs):
        gate.wait(timeout=5.0)
        exported.extend(d["trace_id"] for d in docs)

    exporter = MagicMock()
    exporter.export_docs_batch.side_effect = slow_batch
    tracer = Tracer(
        exporters=[exporter],
        background_export=True,
        export_queue_size=1,
        flush_at=1,
        flush_interval=0.05,
    )

    with caplog.at_level(logging.WARNING, logger="tracecast"):
        with tracer.trace("t1"):
            pass
        time.sleep(0.05)
        with tracer.trace("t2"):
            pass
        time.sleep(0.05)
        with tracer.trace("t3"):
            pass
        time.sleep(0.05)
        dropped = tracer._export_worker.dropped
        gate.set()
        assert tracer.flush(timeout=2.0) is True

    assert dropped >= 1
    assert any("export queue full" in r.getMessage() for r in caplog.records)
    assert 1 <= len(exported) <= 2


def test_batch_flush_at_batches_multiple_traces():
    batches = []

    def capture(docs):
        batches.append(list(docs))

    exporter = MagicMock()
    exporter.export_docs_batch.side_effect = capture
    tracer = Tracer(
        exporters=[exporter],
        background_export=True,
        export_queue_size=50,
        flush_at=3,
        flush_interval=2.0,
        max_batch_bytes=10_000_000,
    )
    for i in range(3):
        with tracer.trace(f"b{i}"):
            pass
    assert tracer.flush(timeout=2.0) is True
    flat = [doc for batch in batches for doc in batch]
    assert len(flat) == 3
    assert any(len(b) >= 2 for b in batches) or len(batches) == 1


def test_flush_without_background_is_noop():
    exporter = MagicMock()
    tracer = Tracer(exporters=[exporter], background_export=False)
    with tracer.trace("sync"):
        pass
    assert tracer.flush() is True
    exporter.export.assert_called_once()


def test_sample_rate_zero_skips_export():
    exporter = MagicMock()
    tracer = Tracer(exporters=[exporter], sample_rate=0.0)
    with tracer.trace("nope"):
        pass
    exporter.export.assert_not_called()


def test_export_worker_unit_flush_and_order():
    seen = []
    worker = ExportWorker(
        lambda batch: seen.extend(batch),
        maxsize=10,
        flush_at=1,
        flush_interval=0.05,
    )
    assert worker.enqueue("a")
    assert worker.enqueue("b")
    assert worker.flush(timeout=2.0)
    assert seen == ["a", "b"]
    worker.shutdown(timeout=2.0)


def test_truncate_payload_default():
    long = "x" * 5000
    out = truncate_payload(long)
    assert out is not None
    assert out.endswith("...")
    assert len(out) == max_payload_chars() + 3


def test_truncate_payload_zero_drops():
    assert truncate_payload("hello", limit=0) is None


def test_truncate_payload_unlimited():
    text = "y" * 10_000
    assert truncate_payload(text, limit=-1) == text
