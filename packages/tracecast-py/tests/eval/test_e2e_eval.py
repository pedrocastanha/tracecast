import pytest

from tracecast import Tracer
from tracecast.eval import evaluator, run_evaluation, clear_registry
from tracecast.eval.dataset import parse_dataset
from tracecast.eval.judge import JudgeResult
from tracecast.eval.models import CriterionScore
from tracecast.exporters.dict_exporter import DictExporter

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeJudge:
    def score(self, *, input, output, expected, criteria):
        val = 1.0 if expected and expected in (output or "") else 0.0
        return JudgeResult(
            scores=[CriterionScore(name=c["name"], score=val, kind="llm", reasoning="fake") for c in criteria],
            tokens_in=4, tokens_out=2, cost_usd=0.0005,
        )


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def test_e2e_eval_pipeline():
    dataset = parse_dataset({
        "name": "suporte",
        "criteria": [{"name": "correct", "description": "responde certo"}],
        "threshold": 0.5,
        "cases": [
            {"id": "single", "input": "horario?", "expected": "echo:horario?"},
            {"id": "multi", "turns": [
                {"role": "user", "content": "oi"},
                {"role": "assistant", "expected": "echo:oi"},
                {"role": "user", "content": "tchau"},
                {"role": "assistant", "expected": "echo:tchau"},
            ]},
        ],
    })

    @evaluator(dataset="unused.json", name="suporte_bot",
               criteria=[{"name": "correct", "description": "responde certo"}],
               scorers=["contains"], threshold=0.5, project_id="suporte")
    def suporte_bot(messages):
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"echo:{last}"

    exporter = DictExporter()
    run = run_evaluation("suporte_bot", exporters=[exporter], dataset=dataset, judge=FakeJudge())

    assert run.total_cases == 2
    assert run.passed == 2
    assert run.pass_rate == 1.0
    assert run.judge_tokens > 0

    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    client = TestClient(app)

    listing = client.get("/tc/api/evals").json()
    assert listing["total"] == 1

    detail = client.get(f"/tc/api/evals/{run.run_id}").json()
    cases = {c["case_id"]: c for c in detail["cases"]}
    assert len(cases["multi"]["turns"]) == 2
    judge_scores = [s for s in cases["single"]["turns"][0]["scores"] if s["kind"] == "llm"]
    assert judge_scores and judge_scores[0]["name"] == "correct"
    assert any(s["kind"] == "deterministic" for s in cases["single"]["turns"][0]["scores"])

    trace_id = cases["multi"]["trace_id"]
    assert client.get(f"/tc/api/traces/{trace_id}").status_code == 200
    graph = client.get(f"/tc/api/traces/{trace_id}/graph")
    assert graph.status_code == 200
