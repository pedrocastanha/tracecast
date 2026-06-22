from datetime import datetime, timezone, timedelta

import pytest

from tracecast import Tracer
from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType
from tracecast.dashboard.reader import TraceReader

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _trace(trace_id, project_id, offset_min=0):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(minutes=offset_min)
    t = Trace(trace_id=trace_id, name="req", started_at=base, project_id=project_id)
    root = Span(span_id=f"{trace_id}-root", type=SpanType.AGENT, name="graph", started_at=base)
    child = Span(span_id=f"{trace_id}-llm", parent_span_id=f"{trace_id}-root",
                 type=SpanType.LLM, name="llm:gpt-4o", model="gpt-4o",
                 started_at=base + timedelta(seconds=1),
                 finished_at=base + timedelta(seconds=2),
                 tokens_in=10, tokens_out=5)
    t.spans = [root, child]
    t.finished_at = base + timedelta(seconds=3)
    t._finalize()
    return t


class FakeReadableExporter:
    def __init__(self, traces):
        self._docs = [t.to_dict() for t in traces]

    def export(self, trace):
        self._docs.append(trace.to_dict())

    def _match(self, d, project_name, project_id, from_dt, to_dt):
        if project_name and d.get("project_name") != project_name:
            return False
        if project_id and d.get("project_id") != project_id:
            return False
        return True

    def query(self, *, project_name=None, project_id=None, user_id=None, session_id=None,
              from_dt=None, to_dt=None, limit=50, offset=0, sort_by="date", order="desc"):
        rows = [d for d in self._docs if self._match(d, project_name, project_id, from_dt, to_dt)]
        rows.sort(key=lambda d: d["started_at"], reverse=(order == "desc"))
        return rows[offset:offset + limit]

    def count(self, *, project_name=None, project_id=None, user_id=None, session_id=None, from_dt=None, to_dt=None):
        return len([d for d in self._docs if self._match(d, project_name, project_id, from_dt, to_dt)])

    def get(self, trace_id):
        return next((d for d in self._docs if d["trace_id"] == trace_id), None)


def _client(exporter):
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    return TestClient(app)


def test_query_page_pushdown_filters_by_project():
    exporter = FakeReadableExporter([
        _trace("t1", "p1", 0), _trace("t2", "p2", 1), _trace("t3", "p1", 2),
    ])
    reader = TraceReader([exporter])
    page, total = reader.query_page(page=1, page_size=10, project_id="p1")
    assert total == 2
    assert {t.trace_id for t in page} == {"t1", "t3"}


def test_api_traces_uses_pushdown():
    exporter = FakeReadableExporter([_trace("t1", "p1"), _trace("t2", "p2")])
    client = _client(exporter)
    resp = client.get("/tc/api/traces", params={"project_id": "p1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["traces"][0]["trace_id"] == "t1"


def test_api_graph_endpoint():
    exporter = FakeReadableExporter([_trace("t1", "p1")])
    client = _client(exporter)
    resp = client.get("/tc/api/traces/t1/graph")
    assert resp.status_code == 200
    g = resp.json()
    assert {n["id"] for n in g["nodes"]} == {"t1-root"}
    assert g["edges"] == [] or all("from" in e for e in g["edges"])
    root_node = next(n for n in g["nodes"] if n["id"] == "t1-root")
    assert root_node["own_total_tokens"] == 15
    assert root_node["primary_model"] == "gpt-4o"
    assert len(root_node["llm_calls"]) == 1
    assert g["total_tokens"] == 15


def test_api_graph_404():
    exporter = FakeReadableExporter([])
    client = _client(exporter)
    assert client.get("/tc/api/traces/missing/graph").status_code == 404


def test_index_injects_prefix():
    exporter = FakeReadableExporter([])
    client = _client(exporter)
    resp = client.get("/tc/")
    assert resp.status_code == 200
    assert 'window.__TC_PREFIX__ = "/tc"' in resp.text
