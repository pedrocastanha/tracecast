import pytest

from tracecast.eval import evaluator, run_evaluation, clear_registry
from tracecast.eval.dataset import parse_dataset
from tracecast.eval.judge import JudgeResult
from tracecast.eval.models import CriterionScore
from tracecast.exporters.dict_exporter import DictExporter


class FakeJudge:
    def score(self, *, input, output, expected, criteria):
        val = 1.0 if (expected and expected in (output or "")) else 0.0
        return JudgeResult(
            scores=[CriterionScore(name=c["name"], score=val, kind="llm") for c in criteria],
            tokens_in=5, tokens_out=3, cost_usd=0.001,
        )


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _dataset():
    return parse_dataset({
        "name": "d",
        "criteria": [{"name": "correct", "description": "x"}],
        "threshold": 0.5,
        "cases": [
            {"id": "c1", "input": "hi", "expected": "answer: hi"},
            {"id": "c2", "input": "yo", "expected": "WRONG"},
            {"id": "err", "input": "boom", "expected": "x"},
        ],
    })


def test_run_evaluation_single_turn():
    @evaluator(dataset="unused.json", name="bot", criteria=[{"name": "correct", "description": "x"}],
               scorers=["contains"], threshold=0.5, project_id="proj")
    def bot(text):
        if text == "boom":
            raise RuntimeError("kaboom")
        return f"answer: {text}"

    exporter = DictExporter()
    run = run_evaluation("bot", exporters=[exporter], dataset=_dataset(), judge=FakeJudge())

    assert run.total_cases == 3
    assert run.passed == 1
    assert run.failed == 2
    assert run.pass_rate == pytest.approx(1 / 3)
    assert run.avg_score == pytest.approx(0.5)
    assert run.judge_tokens == 8 * 2  # 2 non-error cases, (5+3) each
    assert run.project_id == "proj"

    by_id = {c.case_id: c for c in run.cases}
    assert by_id["c1"].passed is True
    assert by_id["c2"].passed is False
    assert by_id["err"].status == "error"
    assert by_id["err"].error == "kaboom"
    assert by_id["c1"].trace_id is not None

    assert len(exporter.evals) == 1
    assert len(exporter.traces) == 3  # one trace per case


def test_run_evaluation_multi_turn_history_aware():
    @evaluator(dataset="unused.json", name="conv", criteria=[], scorers=["contains"], threshold=0.5)
    def conv(messages):
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"echo:{last}"

    ds = parse_dataset({
        "name": "c",
        "cases": [{
            "id": "m1",
            "turns": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "expected": "echo:one"},
                {"role": "user", "content": "two"},
                {"role": "assistant", "expected": "echo:two"},
            ],
        }],
    })

    exporter = DictExporter()
    run = run_evaluation("conv", exporters=[exporter], dataset=ds, judge=FakeJudge())
    case = run.cases[0]
    assert len(case.turns) == 2
    assert case.turns[0].output == "echo:one"
    assert case.turns[1].output == "echo:two"
    assert case.passed is True


def test_run_evaluation_resolves_registered_dataset(tmp_path):
    import json
    p = tmp_path / "ds.json"
    p.write_text(json.dumps({"name": "f", "cases": [{"id": "c", "input": "hi", "expected": "answer: hi"}]}))

    @evaluator(dataset=str(p), name="bot2", scorers=["contains"], threshold=0.5)
    def bot2(text):
        return f"answer: {text}"

    run = run_evaluation("bot2", exporters=[DictExporter()], judge=FakeJudge())
    assert run.dataset_name == "f"
    assert run.total_cases == 1
    assert run.passed == 1
