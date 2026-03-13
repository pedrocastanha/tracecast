import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from tracecast.exporters.json_file import JsonFileExporter
from tracecast.models.trace import Trace


def _make_trace(trace_id="t1"):
    t = Trace(trace_id=trace_id, name="test", started_at=datetime.now(timezone.utc))
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    return t

def test_exporta_trace_em_jsonl():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    exporter = JsonFileExporter(path=path)
    exporter.export(_make_trace("t1"))
    exporter.export(_make_trace("t2"))
    lines = Path(path).read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["trace_id"] == "t1"
    assert json.loads(lines[1])["trace_id"] == "t2"


def test_cada_linha_e_json_valido():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    exporter = JsonFileExporter(path=path)
    t = _make_trace("json-check")
    t.metadata = {"user": "alice"}
    exporter.export(t)
    parsed = json.loads(Path(path).read_text().strip())
    assert parsed["trace_id"] == "json-check"
    assert parsed["metadata"]["user"] == "alice"

def test_cria_diretorio_pai_automaticamente():
    with tempfile.TemporaryDirectory() as tmp:
        nested_path = str(Path(tmp) / "logs" / "nested" / "traces.jsonl")
        exporter = JsonFileExporter(path=nested_path)
        exporter.export(_make_trace("nested-1"))
        assert Path(nested_path).exists()
        lines = Path(nested_path).read_text().strip().splitlines()
        assert json.loads(lines[0])["trace_id"] == "nested-1"

def test_aexport_async():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name

    exporter = JsonFileExporter(path=path)

    async def run():
        await exporter.aexport(_make_trace("async-t1"))
        await exporter.aexport(_make_trace("async-t2"))

    asyncio.run(run())
    lines = Path(path).read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["trace_id"] == "async-t1"
    assert json.loads(lines[1])["trace_id"] == "async-t2"
