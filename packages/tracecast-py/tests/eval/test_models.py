from datetime import datetime, timezone, timedelta

from tracecast.eval.models import CriterionScore, TurnResult, EvalCase, EvalRun, SCHEMA_VERSION


def _turn(scores):
    t = TurnResult(index=0, role="assistant", input="i", output="o", expected="e",
                   scores=[CriterionScore(name=n, score=s) for n, s in scores])
    return t


def test_turn_compute_overall_and_pass():
    t = _turn([("a", 0.8), ("b", 0.6)])
    t.compute(threshold=0.7)
    assert t.overall_score == 0.7
    assert t.passed is True
    t2 = _turn([("a", 0.4)])
    t2.compute(0.7)
    assert t2.passed is False


def test_case_error_not_passed():
    c = EvalCase(case_id="c", status="error", error="boom")
    c.compute(0.5)
    assert c.passed is False
    assert c.status == "error"


def test_run_finalize_aggregates():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = EvalRun(run_id="r", name="n", started_at=base, threshold=0.5)
    good = EvalCase(case_id="c1")
    good.turns = [_turn([("a", 1.0)])]
    for t in good.turns:
        t.compute(0.5)
    good.compute(0.5)
    bad = EvalCase(case_id="c2")
    bad.turns = [_turn([("a", 0.0)])]
    for t in bad.turns:
        t.compute(0.5)
    bad.compute(0.5)
    run.cases = [good, bad]
    run.finished_at = base + timedelta(seconds=2)
    run.finalize()

    assert run.total_cases == 2
    assert run.passed == 1
    assert run.failed == 1
    assert run.pass_rate == 0.5
    assert run.avg_score == 0.5
    assert run.latency_ms == 2000


def test_run_roundtrip():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = EvalRun(run_id="r", name="n", started_at=base, criteria=["a"], threshold=0.7)
    c = EvalCase(case_id="c1", trace_id="trace-1")
    c.turns = [_turn([("a", 0.9)])]
    c.turns[0].compute(0.7)
    c.compute(0.7)
    run.cases = [c]
    run.finished_at = base
    run.finalize()

    d = run.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    restored = EvalRun.from_dict(d)
    assert restored.run_id == "r"
    assert restored.cases[0].trace_id == "trace-1"
    assert restored.cases[0].turns[0].scores[0].name == "a"
    assert restored.pass_rate == run.pass_rate
