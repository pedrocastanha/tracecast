import pytest

from tracecast.eval.compare import compare


def _run(run_id, dataset, cases, avg, pass_rate=1.0):
    return {
        "run_id": run_id, "dataset_name": dataset,
        "avg_score": avg, "pass_rate": pass_rate,
        "cases": [{"case_id": cid, "overall_score": sc, "passed": sc >= 0.5}
                  for cid, sc in cases],
    }


def test_compare_case_and_aggregate_deltas():
    a = _run("a", "d", [("c1", 0.5)], avg=0.5)
    b = _run("b", "d", [("c1", 0.8)], avg=0.8)
    res = compare(a, b)
    assert res["avg_score_delta"] == pytest.approx(0.3)
    assert res["dataset_mismatch"] is False
    c1 = res["cases"][0]
    assert c1["delta"] == pytest.approx(0.3)
    assert c1["status"] == "changed"


def test_compare_added_and_removed():
    a = _run("a", "d", [("c1", 0.5)], avg=0.5)
    b = _run("b", "d", [("c1", 0.5), ("c2", 0.9)], avg=0.7)
    res = compare(a, b)
    by_id = {c["case_id"]: c for c in res["cases"]}
    assert by_id["c2"]["status"] == "added"

    res2 = compare(b, a)
    by_id2 = {c["case_id"]: c for c in res2["cases"]}
    assert by_id2["c2"]["status"] == "removed"


def test_compare_dataset_mismatch_flagged():
    a = _run("a", "d1", [("c1", 0.5)], avg=0.5)
    b = _run("b", "d2", [("c1", 0.5)], avg=0.5)
    assert compare(a, b)["dataset_mismatch"] is True


def test_compare_endpoint():
    import tracecast
    from tracecast import Tracer
    from tracecast.eval import evaluator, run_evaluation, clear_registry
    from tracecast.eval.dataset import parse_dataset
    from tracecast.exporters.dict_exporter import DictExporter
    fastapi = pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    clear_registry()
    exp = DictExporter()

    @evaluator(dataset="x", name="bot", scorers=["contains"], threshold=0.5)
    def bot(text):
        return f"answer: {text}"

    ds = parse_dataset({"name": "d", "cases": [{"id": "c1", "input": "hi", "expected": "answer: hi"}]})
    r1 = run_evaluation("bot", exporters=[exp], dataset=ds)
    r2 = run_evaluation("bot", exporters=[exp], dataset=ds)

    tracer = Tracer(exporters=[exp])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    client = TestClient(app)

    resp = client.get("/tc/api/evals/compare", params={"a": r1.run_id, "b": r2.run_id})
    assert resp.status_code == 200
    assert resp.json()["dataset_mismatch"] is False
    assert client.get("/tc/api/evals/compare", params={"a": r1.run_id, "b": "ghost"}).status_code == 404
    clear_registry()
