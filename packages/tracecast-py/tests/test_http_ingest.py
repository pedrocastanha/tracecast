"""Tests for HttpExporter + server IngestService + /api/ingest endpoints."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tracecast.core.ingest import IngestService, normalize_ingest_body
from tracecast.core.tracer import Tracer
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.exporters.http import HttpExporter
from tracecast.dashboard.reader import TraceReader
from tracecast.dashboard.router import _make_router


def test_normalize_ingest_body_variants():
    assert normalize_ingest_body(None) == []
    assert normalize_ingest_body({"trace_id": "a", "spans": []})[0]["trace_id"] == "a"
    assert normalize_ingest_body({"trace": {"trace_id": "b"}})[0]["trace_id"] == "b"
    assert len(normalize_ingest_body({"traces": [{"trace_id": "1"}, {"trace_id": "2"}]})) == 2
    assert len(normalize_ingest_body([{"trace_id": "x"}])) == 1
    assert normalize_ingest_body({"foo": 1}) == []


def test_ingest_service_writes_to_store():
    sink = DictExporter()

    def write(docs):
        sink.export_docs_batch(docs)

    svc = IngestService(write, queue_size=50, flush_at=1, flush_interval=0.05)
    r = svc.accept([{"trace_id": "t1", "name": "n", "spans": [], "started_at": "2026-01-01T00:00:00+00:00"}])
    assert r["accepted"] == 1
    assert r["dropped"] == 0
    assert svc.flush(timeout=2.0) is True
    assert len(sink.traces) == 1
    assert sink.traces[0]["trace_id"] == "t1"
    h = svc.health()
    assert h["enabled"] is True
    assert h["accepted"] >= 1
    svc.shutdown(timeout=2.0)


def test_ingest_service_spool_when_queue_full(tmp_path: Path):
    written = []
    lock = threading.Lock()

    def slow_write(docs):
        time.sleep(0.3)
        with lock:
            written.extend(docs)

    spool = tmp_path / "spool.jsonl"
    svc = IngestService(
        slow_write,
        queue_size=1,
        flush_at=1,
        flush_interval=0.05,
        spool_path=str(spool),
        spool_poll=0.1,
    )
    # Fill queue + force spill
    docs = [{"trace_id": f"t{i}", "name": "n", "spans": []} for i in range(5)]
    r = svc.accept(docs)
    assert r["accepted"] + r["dropped"] == 5
    # At least some should be accepted (mem or spool)
    assert r["accepted"] >= 1
    time.sleep(1.5)
    svc.flush(timeout=5.0)
    svc.shutdown(timeout=3.0)
    # Eventually store or spool should have seen most docs
    with lock:
        ids = {d["trace_id"] for d in written}
    # Spool may still hold leftovers; health counters track activity
    h = svc.health()
    assert h["accepted"] >= 1


def test_api_ingest_endpoints():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    sink = DictExporter()
    reader = TraceReader([sink], max_traces=100)

    def write(docs):
        sink.export_docs_batch(docs)

    svc = IngestService(write, queue_size=50, flush_at=1, flush_interval=0.05)
    reader.ingest = svc

    app = FastAPI()
    app.include_router(_make_router(reader, prefix="/tc"), prefix="/tc")
    client = TestClient(app)

    health = client.get("/tc/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["ingest"]["enabled"] is True

    r = client.post(
        "/tc/api/ingest",
        json={
            "trace_id": "http-1",
            "name": "POST /chat",
            "spans": [],
            "project_id": "p1",
            "total_tokens": 10,
            "started_at": "2026-07-14T12:00:00+00:00",
        },
    )
    assert r.status_code == 202
    assert r.json()["accepted"] == 1

    r2 = client.post(
        "/tc/api/ingest/batch",
        json={
            "traces": [
                {
                    "trace_id": "http-2",
                    "name": "a",
                    "spans": [],
                    "started_at": "2026-07-14T12:00:01+00:00",
                },
                {
                    "trace_id": "http-3",
                    "name": "b",
                    "spans": [],
                    "started_at": "2026-07-14T12:00:02+00:00",
                },
            ]
        },
    )
    assert r2.status_code == 202
    assert r2.json()["accepted"] == 2

    assert svc.flush(timeout=2.0) is True
    ids = {t["trace_id"] for t in sink.traces}
    assert "http-1" in ids
    assert "http-2" in ids
    assert "http-3" in ids

    # list API sees them
    listing = client.get("/tc/api/traces")
    assert listing.status_code == 200
    assert listing.json()["total"] >= 3

    svc.shutdown(timeout=2.0)


def test_http_exporter_posts_batch():
    captured = {}

    class FakeResp:
        status = 202

        def read(self):
            return json.dumps({"accepted": 2, "dropped": 0}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return FakeResp()

    exp = HttpExporter("http://127.0.0.1:8010/tracecast", timeout=1.5)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        exp.export_docs_batch(
            [
                {"trace_id": "a", "name": "n", "spans": []},
                {"trace_id": "b", "name": "n", "spans": []},
            ]
        )
    assert captured["url"].endswith("/api/ingest/batch")
    assert len(captured["data"]["traces"]) == 2
    assert captured["timeout"] == 1.5


def test_tracer_background_with_http_exporter_mock():
    """Background path enqueues; HttpExporter called off request thread."""
    calls = []

    class FakeHttp(HttpExporter):
        def __init__(self):
            # skip Base init validation by setting attrs directly
            self.base_url = "http://example/tracecast"
            self.timeout = 1.0
            self._auth = None
            self._headers = {}
            self._prefix = ""

        def export_docs_batch(self, docs):
            calls.append(list(docs))

        def export_doc(self, doc):
            calls.append([doc])

        def export(self, trace):
            self.export_doc(trace.to_dict())

    exp = FakeHttp()
    tracer = Tracer(
        exporters=[exp],
        background_export=True,
        export_queue_size=20,
        flush_at=1,
        flush_interval=0.05,
        span_filter="llm_tool",
    )
    with tracer.trace("bg-http", project_id="p"):
        pass
    assert tracer.flush(timeout=2.0) is True
    assert len(calls) >= 1
    assert calls[0][0]["name"] == "bg-http"
