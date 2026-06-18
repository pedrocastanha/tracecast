import json
import pytest

from tracecast.eval.dataset import add_to_dataset, load_dataset


def test_creates_file_and_appends_case(tmp_path):
    path = tmp_path / "ds.json"
    trace = {"trace_id": "t1", "spans": [{"input": "What is 2+2?", "output": "4"}]}
    add_to_dataset(trace, str(path), expected="4")

    data = json.loads(path.read_text())
    assert data["cases"][0]["input"] == "What is 2+2?"
    assert data["cases"][0]["expected"] == "4"

    add_to_dataset({"trace_id": "t2", "spans": [{"input": "hi"}]}, str(path), expected="hello")
    data = json.loads(path.read_text())
    assert len(data["cases"]) == 2
    # resulting file is a loadable golden dataset
    ds = load_dataset(str(path))
    assert len(ds.cases) == 2


def test_explicit_input_overrides_derivation(tmp_path):
    path = tmp_path / "ds.json"
    add_to_dataset({"trace_id": "t1", "spans": []}, str(path), input="manual q", expected="a")
    data = json.loads(path.read_text())
    assert data["cases"][0]["input"] == "manual q"


def test_resolve_trace_by_id_via_exporter(tmp_path):
    from tracecast.exporters.dict_exporter import DictExporter
    exp = DictExporter()
    exp.traces.append({"trace_id": "tX", "spans": [{"input": "q from prod", "output": "r"}]})
    path = tmp_path / "ds.json"
    add_to_dataset("tX", str(path), expected="r", exporters=[exp])
    data = json.loads(path.read_text())
    assert data["cases"][0]["input"] == "q from prod"


def test_missing_trace_raises(tmp_path):
    with pytest.raises(ValueError):
        add_to_dataset("ghost", str(tmp_path / "ds.json"), exporters=[])
