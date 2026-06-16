import json

import pytest

from tracecast.eval.dataset import parse_dataset, load_dataset


def test_parse_single_turn():
    ds = parse_dataset({
        "name": "d",
        "criteria": [{"name": "x", "description": "y"}],
        "threshold": 0.6,
        "cases": [{"id": "c1", "input": "oi", "expected": "tchau", "metadata": {"t": 1}}],
    })
    assert ds.name == "d"
    assert ds.threshold == 0.6
    case = ds.cases[0]
    assert [t.role for t in case.turns] == ["user", "assistant"]
    assert case.turns[0].content == "oi"
    assert case.turns[1].expected == "tchau"
    assert case.metadata == {"t": 1}


def test_parse_multi_turn():
    ds = parse_dataset({
        "name": "d",
        "cases": [{
            "id": "c1",
            "turns": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "expected": "b"},
                {"role": "user", "content": "c"},
                {"role": "assistant", "expected": "d"},
            ],
        }],
    })
    turns = ds.cases[0].turns
    assert len(turns) == 4
    assert turns[1].expected == "b"
    assert turns[3].expected == "d"


def test_empty_cases_raises():
    with pytest.raises(ValueError):
        parse_dataset({"name": "d", "cases": []})


def test_case_without_input_or_turns_raises():
    with pytest.raises(ValueError):
        parse_dataset({"cases": [{"id": "bad"}]})


def test_turn_without_role_raises():
    with pytest.raises(ValueError):
        parse_dataset({"cases": [{"id": "c", "turns": [{"content": "x"}]}]})


def test_load_dataset_from_file(tmp_path):
    p = tmp_path / "ds.json"
    p.write_text(json.dumps({"name": "f", "cases": [{"id": "c", "input": "i", "expected": "e"}]}))
    ds = load_dataset(str(p))
    assert ds.name == "f"
    assert ds.path == str(p)


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_dataset("/nope/missing.json")
