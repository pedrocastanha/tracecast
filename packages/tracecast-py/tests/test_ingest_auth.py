import os
from unittest.mock import patch

from tracecast.core.ingest_auth import check_ingest_authorized, ingest_token


def test_open_when_no_token(monkeypatch):
    monkeypatch.delenv("TRACECAST_INGEST_TOKEN", raising=False)
    monkeypatch.delenv("TRACECAST_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("TRACECAST_INGEST_AUTH_REQUIRED", raising=False)
    assert check_ingest_authorized(authorization=None, x_token=None) is True


def test_token_header(monkeypatch):
    monkeypatch.setenv("TRACECAST_INGEST_TOKEN", "secret-1")
    assert check_ingest_authorized(x_token="secret-1") is True
    assert check_ingest_authorized(x_token="wrong") is False
    assert check_ingest_authorized(authorization="Bearer secret-1") is True
    assert check_ingest_authorized(authorization="Bearer nope") is False


def test_api_ingest_requires_token():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tracecast.dashboard.reader import TraceReader
    from tracecast.dashboard.router import _make_router
    from tracecast.core.ingest import IngestService
    from tracecast.exporters.dict_exporter import DictExporter

    sink = DictExporter()
    reader = TraceReader([sink])
    reader.ingest = IngestService(lambda docs: sink.export_docs_batch(docs), flush_at=1, flush_interval=0.05)
    app = FastAPI()
    app.include_router(_make_router(reader, prefix="/tc"), prefix="/tc")
    client = TestClient(app)

    with patch.dict(os.environ, {"TRACECAST_INGEST_TOKEN": "tok"}, clear=False):
        r = client.post("/tc/api/ingest", json={"trace_id": "a", "name": "n", "spans": []})
        assert r.status_code == 401
        r2 = client.post(
            "/tc/api/ingest",
            json={"trace_id": "b", "name": "n", "spans": [], "total_tokens": 9},
            headers={"X-TraceCast-Token": "tok"},
        )
        assert r2.status_code == 202
        assert r2.json()["accepted"] == 1
        reader.ingest.flush(timeout=2.0)
        assert any(t.get("trace_id") == "b" for t in sink.traces)
        reader.ingest.shutdown(timeout=1.0)
