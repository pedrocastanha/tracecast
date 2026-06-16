import pytest

from tracecast import Tracer
from tracecast.eval import evaluator, run_evaluation, clear_registry
from tracecast.eval.dataset import parse_dataset
from tracecast.exporters.dict_exporter import DictExporter

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _dataset():
    return parse_dataset({
        "name": "d",
        "cases": [{"id": "c1", "input": "hi", "expected": "answer: hi"}],
    })


def _bot_target():
    @evaluator(dataset="unused.json", name="bot", scorers=["contains"], threshold=0.5, project_id="proj")
    def bot(text):
        return f"answer: {text}"
    return "bot"


def _client(exporter):
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    return TestClient(app)


def test_api_evals_list_and_detail():
    exporter = DictExporter()
    _bot_target()
    run = run_evaluation("bot", exporters=[exporter], dataset=_dataset())

    client = _client(exporter)
    listing = client.get("/tc/api/evals", params={"project_id": "proj"})
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["evals"][0]["run_id"] == run.run_id
    assert "cases" not in body["evals"][0]

    detail = client.get(f"/tc/api/evals/{run.run_id}")
    assert detail.status_code == 200
    full = detail.json()
    assert full["cases"][0]["turns"][0]["output"] == "answer: hi"
    assert full["cases"][0]["trace_id"] is not None


def test_api_evals_filter_excludes():
    exporter = DictExporter()
    _bot_target()
    run_evaluation("bot", exporters=[exporter], dataset=_dataset())
    client = _client(exporter)
    assert client.get("/tc/api/evals", params={"project_id": "nope"}).json()["total"] == 0


def test_api_eval_run_trigger(tmp_path):
    import json
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps({"name": "d", "cases": [{"id": "c1", "input": "hi", "expected": "answer: hi"}]}))

    @evaluator(dataset=str(ds), name="bot", scorers=["contains"], threshold=0.5, project_id="proj")
    def bot(text):
        return f"answer: {text}"

    exporter = DictExporter()
    client = _client(exporter)
    resp = client.post("/tc/api/evals/run", json={"target": "bot"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cases"] == 1
    assert body["passed"] == 1
    assert len(exporter.evals) == 1


def test_api_eval_run_404_unknown_target():
    exporter = DictExporter()
    _bot_target()
    client = _client(exporter)
    resp = client.post("/tc/api/evals/run", json={"target": "ghost"})
    assert resp.status_code == 404


def test_api_eval_run_501_when_no_targets():
    exporter = DictExporter()
    client = _client(exporter)
    resp = client.post("/tc/api/evals/run", json={"target": "x"})
    assert resp.status_code == 501
