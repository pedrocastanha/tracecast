import pytest

from tracecast.eval.metrics import (
    METRICS, Metric, register_metric, resolve_metrics, split_metrics, toxicity_score,
)
from tracecast.eval.scorers import SCORERS


def test_llm_presets_exist():
    for n in ["faithfulness", "answer_relevancy", "context_precision",
              "context_recall", "hallucination", "conciseness"]:
        assert n in METRICS
        assert METRICS[n].kind == "llm"
        assert METRICS[n].description


def test_resolve_metrics_to_criteria():
    crit = resolve_metrics(["faithfulness", "answer_relevancy"])
    assert [c["name"] for c in crit] == ["faithfulness", "answer_relevancy"]
    assert all(c["description"] for c in crit)


def test_faithfulness_needs_context():
    assert METRICS["faithfulness"].needs_context is True
    assert METRICS["answer_relevancy"].needs_context is False


def test_unknown_metric_raises():
    with pytest.raises(ValueError):
        resolve_metrics(["does_not_exist"])


def test_split_metrics_separates_llm_and_heuristic():
    llm, heur = split_metrics(["faithfulness", "toxicity"])
    assert [c["name"] for c in llm] == ["faithfulness"]
    assert heur == ["toxicity"]


def test_toxicity_is_registered_heuristic():
    assert "toxicity" in METRICS
    assert METRICS["toxicity"].kind == "heuristic"
    assert "toxicity" in SCORERS


def test_toxicity_score_detects_toxic_vs_neutral():
    assert toxicity_score("You are a stupid idiot", "") > 0
    assert toxicity_score("Have a great day, thank you!", "") == 0.0


def test_register_custom_metric():
    register_metric(Metric(name="my_metric", kind="llm", description="custom rubric"))
    assert resolve_metrics(["my_metric"])[0]["description"] == "custom rubric"
