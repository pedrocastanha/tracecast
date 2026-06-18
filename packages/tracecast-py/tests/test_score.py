import pytest
from datetime import datetime, timezone

from tracecast.models.score import Score


def test_numeric_score_roundtrip():
    s = Score(trace_id="t1", name="quality", value=0.8)
    s.validate()
    d = s.to_dict()
    assert d["trace_id"] == "t1"
    assert d["name"] == "quality"
    assert d["value"] == 0.8
    assert d["data_type"] == "numeric"
    assert d["kind"] == "human"
    back = Score.from_dict(d)
    assert back.trace_id == "t1"
    assert back.value == 0.8


def test_boolean_score_rejects_non_binary():
    Score(trace_id="t1", name="thumb", value=1, data_type="boolean").validate()
    Score(trace_id="t1", name="thumb", value=0, data_type="boolean").validate()
    with pytest.raises(ValueError):
        Score(trace_id="t1", name="thumb", value=0.5, data_type="boolean").validate()


def test_categorical_requires_string_value():
    with pytest.raises(ValueError):
        Score(trace_id="t1", name="sentiment", value=0, data_type="categorical").validate()
    ok = Score(trace_id="t1", name="sentiment", value=2,
               data_type="categorical", string_value="positive")
    ok.validate()
    assert ok.to_dict()["string_value"] == "positive"


def test_invalid_data_type_rejected():
    with pytest.raises(ValueError):
        Score(trace_id="t1", name="x", value=1, data_type="bogus").validate()


def test_invalid_kind_rejected():
    with pytest.raises(ValueError):
        Score(trace_id="t1", name="x", value=1, kind="robot").validate()


def test_score_has_id_and_created_at():
    s = Score(trace_id="t1", name="x", value=1)
    assert s.score_id
    assert isinstance(s.created_at, datetime)


def test_span_id_optional():
    s = Score(trace_id="t1", span_id="sp1", name="x", value=1)
    assert s.to_dict()["span_id"] == "sp1"
    assert Score(trace_id="t1", name="x", value=1).to_dict()["span_id"] is None
