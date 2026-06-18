import pytest

import tracecast
from tracecast import Tracer, set_default_tracer
from tracecast.exporters.dict_exporter import DictExporter


def test_score_persists_via_explicit_exporter():
    exp = DictExporter()
    s = tracecast.score("t1", name="user_feedback", value=1, comment="useful", exporters=[exp])
    assert s.trace_id == "t1"
    rows = exp.query_scores(trace_id="t1")
    assert len(rows) == 1
    assert rows[0]["name"] == "user_feedback"
    assert rows[0]["comment"] == "useful"
    assert rows[0]["source"] == "sdk"


def test_score_uses_default_tracer_exporters():
    exp = DictExporter()
    set_default_tracer(Tracer(exporters=[exp]))
    try:
        tracecast.score("t2", name="q", value=0.5)
        assert len(exp.query_scores(trace_id="t2")) == 1
    finally:
        set_default_tracer(Tracer(exporters=[]))


def test_invalid_value_rejected_before_persist():
    exp = DictExporter()
    with pytest.raises(ValueError):
        tracecast.score("t1", name="thumb", value=0.5, data_type="boolean", exporters=[exp])
    assert exp.query_scores(trace_id="t1") == []


def test_exporter_failure_does_not_propagate():
    class Boom(DictExporter):
        def export_score(self, score):
            raise RuntimeError("db down")
    s = tracecast.score("t3", name="q", value=1, exporters=[Boom()])
    assert s.trace_id == "t3"  # returned despite export failure


def test_query_scores_filter_by_trace():
    exp = DictExporter()
    tracecast.score("a", name="q", value=1, exporters=[exp])
    tracecast.score("b", name="q", value=1, exporters=[exp])
    assert {r["trace_id"] for r in exp.query_scores(trace_id="a")} == {"a"}
    assert len(exp.query_scores()) == 2
