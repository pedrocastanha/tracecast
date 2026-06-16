import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from tracecast import Tracer
from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType, SpanStatus
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.exporters.json_file import JsonFileExporter
from tracecast.dashboard.reader import TraceReader


def _graph_trace():
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    t = Trace(trace_id="rt", name="req", started_at=base, project_id="p1", session_id="s1")
    root = Span(span_id="root", type=SpanType.AGENT, name="graph", started_at=base,
                finished_at=base + timedelta(milliseconds=5))
    llm = Span(span_id="llm", parent_span_id="root", type=SpanType.LLM, name="llm:gpt-4o",
               model="gpt-4o", started_at=base + timedelta(milliseconds=1),
               finished_at=base + timedelta(milliseconds=3),
               tokens_in=10, tokens_out=5, input="hi", output="ok")
    tool = Span(span_id="tool", parent_span_id="root", type=SpanType.TOOL, name="guard",
                started_at=base + timedelta(milliseconds=4),
                finished_at=base + timedelta(milliseconds=5))
    tool.mark_error("blocked")
    t.spans = [root, llm, tool]
    t.finished_at = base + timedelta(milliseconds=6)
    t._finalize()
    return t


def _assert_equivalent(original: Trace, restored: Trace):
    assert restored.trace_id == original.trace_id
    assert restored.project_id == original.project_id
    assert restored.total_tokens == original.total_tokens
    assert len(restored.spans) == len(original.spans)
    parents = {s.span_id: s.parent_span_id for s in restored.spans}
    assert parents == {"root": None, "llm": "root", "tool": "root"}
    err = next(s for s in restored.spans if s.span_id == "tool")
    assert err.status == SpanStatus.ERROR
    assert err.error == "blocked"
    assert len(restored.edges) == len(original.edges)


def test_roundtrip_dict():
    exporter = DictExporter()
    tracer = Tracer(exporters=[exporter])
    original = _graph_trace()
    exporter.export(original)
    reader = TraceReader([exporter])
    restored = reader.get_trace("rt")
    _assert_equivalent(original, restored)


def test_roundtrip_jsonfile():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    exporter = JsonFileExporter(path=path)
    original = _graph_trace()
    exporter.export(original)
    reader = TraceReader([exporter])
    restored = reader.get_trace("rt")
    _assert_equivalent(original, restored)


class MongoFake:
    def __init__(self, collection):
        self._collection = collection


def test_roundtrip_mongo_reader_reads_collection():
    original = _graph_trace()
    doc = original.to_dict()
    mock_col = MagicMock()
    mock_col.find.return_value.sort.return_value.limit.return_value = [doc]

    exporter = MongoFake(mock_col)

    reader = TraceReader([exporter])
    restored = reader.get_traces()
    assert len(restored) == 1
    _assert_equivalent(original, restored[0])
