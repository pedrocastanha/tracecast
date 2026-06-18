import pytest

from tracecast.eval import evaluator, run_evaluation, clear_registry
from tracecast.eval.dataset import parse_dataset
from tracecast.eval.judge import LLMJudge, JudgeResponse


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def test_runner_resolves_named_llm_metric_with_context():
    captured = {}

    def fake_call(system, user):
        captured["user"] = user
        return JudgeResponse(text='{"faithfulness": {"score": 1.0, "reasoning": "grounded"}}')

    judge = LLMJudge(call_fn=fake_call)

    @evaluator(dataset="x", name="bot", criteria=["faithfulness"], threshold=0.5)
    def bot(text):
        return "Paris is the capital of France."

    ds = parse_dataset({
        "name": "d",
        "cases": [{
            "id": "c1", "input": "capital of France?", "expected": "Paris",
            "context": "France's capital city is Paris.",
        }],
    })
    run = run_evaluation("bot", dataset=ds, judge=judge)
    score = run.cases[0].turns[0].scores[0]
    assert score.name == "faithfulness"
    assert score.score == 1.0
    assert "France's capital city is Paris." in captured["user"]


def test_runner_heuristic_metric_via_scorers():
    @evaluator(dataset="x", name="tb", scorers=["toxicity"], threshold=0.0)
    def tb(text):
        return "you are an idiot"

    ds = parse_dataset({"name": "d", "cases": [{"id": "c1", "input": "hi", "expected": "x"}]})
    run = run_evaluation("tb", dataset=ds)
    scores = {s.name: s.score for s in run.cases[0].turns[0].scores}
    assert "toxicity" in scores
    assert scores["toxicity"] > 0


def test_unknown_named_metric_raises():
    @evaluator(dataset="x", name="bad", criteria=["nonexistent_metric"], threshold=0.5)
    def bad(text):
        return "x"

    ds = parse_dataset({"name": "d", "cases": [{"id": "c1", "input": "hi", "expected": "x"}]})
    with pytest.raises(ValueError):
        run_evaluation("bad", dataset=ds)
