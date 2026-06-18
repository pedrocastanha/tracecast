import pytest

from tracecast import Tracer
from tracecast.eval.online import OnlineEval
from tracecast.exporters.dict_exporter import DictExporter


def _trace_doc(trace_id="t1", output="you are an idiot"):
    return {"trace_id": trace_id, "spans": [{"input": "say something", "output": output}]}


def test_sample_rate_one_writes_score():
    exp = DictExporter()
    oe = OnlineEval(sample_rate=1.0, metrics=["toxicity"], exporters=[exp], background=False)
    oe.maybe_evaluate(_trace_doc())
    rows = exp.query_scores(trace_id="t1")
    assert len(rows) == 1
    assert rows[0]["name"] == "toxicity"
    assert rows[0]["source"] == "online_eval"
    assert rows[0]["value"] > 0


def test_sample_rate_zero_writes_nothing():
    exp = DictExporter()
    oe = OnlineEval(sample_rate=0.0, metrics=["toxicity"], exporters=[exp], background=False)
    oe.maybe_evaluate(_trace_doc())
    assert exp.query_scores() == []


def test_metric_failure_is_best_effort():
    class BoomExp(DictExporter):
        def export_score(self, s):
            raise RuntimeError("down")
    oe = OnlineEval(sample_rate=1.0, metrics=["toxicity"], exporters=[BoomExp()], background=False)
    oe.maybe_evaluate(_trace_doc())  # must not raise


def test_tracer_integration_attaches_score():
    exp = DictExporter()
    oe = OnlineEval(sample_rate=1.0, metrics=["toxicity"], background=False)
    tracer = Tracer(exporters=[exp], online_eval=oe)
    with tracer.trace(name="t") as tr:
        from tracecast.models.span import Span, SpanType
        from datetime import datetime, timezone
        sp = Span(span_id="s1", type=SpanType.LLM, name="llm",
                  started_at=datetime.now(timezone.utc))
        sp.output = "you are stupid"
        tr.spans.append(sp)
    scores = exp.query_scores()
    assert any(s["name"] == "toxicity" and s["source"] == "online_eval" for s in scores)


def test_tracer_without_online_eval_unaffected():
    exp = DictExporter()
    tracer = Tracer(exporters=[exp])
    with tracer.trace(name="t"):
        pass
    assert exp.query_scores() == []
    assert len(exp.traces) == 1
