import pytest

import tracecast
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(exporter):
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    return TestClient(app), tracer


def test_trace_scores_endpoint():
    exp = DictExporter()
    client, _ = _client(exp)
    tracecast.score("t1", name="user_feedback", value=1, comment="good", exporters=[exp])
    tracecast.score("t1", name="quality", value=0.9, exporters=[exp])
    tracecast.score("other", name="quality", value=0.1, exporters=[exp])

    resp = client.get("/tc/api/traces/t1/scores")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    names = {s["name"] for s in body["scores"]}
    assert names == {"user_feedback", "quality"}


def test_trace_scores_empty():
    exp = DictExporter()
    client, _ = _client(exp)
    resp = client.get("/tc/api/traces/nope/scores")
    assert resp.status_code == 200
    assert resp.json() == {"scores": [], "total": 0}


def test_score_reader_list_for_trace():
    from tracecast.dashboard.score_reader import ScoreReader
    exp = DictExporter()
    tracecast.score("t1", name="a", value=1, exporters=[exp])
    reader = ScoreReader([exp])
    rows = reader.list_for_trace("t1")
    assert len(rows) == 1
    assert rows[0]["name"] == "a"
