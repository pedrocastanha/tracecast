import warnings
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tracecast.core.tracer import Tracer
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.models.span import Span, SpanType


def _add_llm_span(t, tin=100, tout=50, cost=0.01):
    t.spans.append(Span(
        span_id="s1",
        type=SpanType.LLM,
        name="llm:test",
        started_at=t.started_at,
        model="gpt-test",
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        input="prompt",
        output="out",
    ))


def test_sync_export_fallback_to_summary():
    bad = MagicMock()
    bad.export.side_effect = IOError("disk full")
    summaries = []
    bad.export_summary.side_effect = lambda s: summaries.append(s)

    good = DictExporter()
    tracer = Tracer(exporters=[bad, good], background_export=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with tracer.trace("POST /chat", project_id="p1", project_name="Bot") as t:
            _add_llm_span(t, 100, 50, 0.01)

    assert len(summaries) == 1
    s = summaries[0]
    assert s["export_status"] == "summary_only"
    assert s["total_tokens"] == 150
    assert s["project_id"] == "p1"
    assert s["name"] == "POST /chat"
    assert s["spans"] == []
    assert len(good.traces) == 1
    assert good.traces[0].get("is_summary") is not True
    assert tracer.stats.snapshot()["summary_fallback"] >= 1
    assert tracer.stats.snapshot()["exported_ok"] >= 1


def test_full_ok_no_summary():
    exp = DictExporter()
    tracer = Tracer(exporters=[exp], background_export=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with tracer.trace("ok", project_id="p"):
            pass
    assert len(exp.traces) == 1
    assert exp.traces[0].get("export_status") != "summary_only"
    assert tracer.stats.snapshot()["summary_fallback"] == 0


def test_background_fallback_summary():
    bad = MagicMock()
    bad.export_docs_batch.side_effect = IOError("mongo down")
    bad.export_doc.side_effect = IOError("mongo down")
    summaries = []
    bad.export_summary.side_effect = lambda s: summaries.append(s)

    tracer = Tracer(
        exporters=[bad],
        background_export=True,
        flush_at=1,
        flush_interval=0.05,
        export_queue_size=20,
    )
    with tracer.trace("bg", project_id="proj", project_name="Cap") as t:
        _add_llm_span(t, 40, 2, 0.001)
    assert tracer.flush(timeout=3.0)
    assert len(summaries) >= 1
    assert summaries[0]["project_id"] == "proj"
    assert summaries[0]["total_tokens"] == 42
    assert tracer.stats.snapshot()["summary_fallback"] >= 1


def test_retry_then_success():
    calls = {"n": 0}
    exp = MagicMock()

    def flaky_export(trace):
        calls["n"] += 1
        if calls["n"] < 2:
            raise IOError("temp")

    exp.export.side_effect = flaky_export
    tracer = Tracer(exporters=[exp], background_export=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with tracer.trace("retry-me"):
            pass
    assert calls["n"] == 2
    exp.export_summary.assert_not_called()
    assert tracer.stats.snapshot()["export_retried"] >= 1
    assert tracer.stats.snapshot()["exported_ok"] >= 1


def test_warn_without_background_on_json():
    from tracecast.exporters.json_file import JsonFileExporter
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "t.jsonl")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Tracer(exporters=[JsonFileExporter(path)], background_export=False)
            assert any("background_export" in str(x.message) for x in w)
