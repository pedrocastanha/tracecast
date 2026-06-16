import json

import pytest

from tracecast.eval import evaluator, clear_registry
from tracecast.eval import cli


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _dataset_file(tmp_path, expected):
    p = tmp_path / "ds.json"
    p.write_text(json.dumps({"name": "d", "cases": [{"id": "c1", "input": "hi", "expected": expected}]}))
    return str(p)


def test_cli_pass_returns_zero(tmp_path):
    ds = _dataset_file(tmp_path, "answer: hi")
    store = str(tmp_path / "out.jsonl")

    @evaluator(dataset=ds, name="botcli", scorers=["contains"], threshold=0.5)
    def botcli(text):
        return f"answer: {text}"

    rc = cli.run(["--target", "botcli", "--store", store])
    assert rc == 0

    from pathlib import Path
    assert Path(store + ".evals.jsonl").exists()


def test_cli_fail_returns_one(tmp_path):
    ds = _dataset_file(tmp_path, "SOMETHING ELSE")
    store = str(tmp_path / "out.jsonl")

    @evaluator(dataset=ds, name="botcli2", scorers=["exact_match"], threshold=0.5)
    def botcli2(text):
        return f"answer: {text}"

    rc = cli.run(["--target", "botcli2", "--store", store])
    assert rc == 1


def test_cli_unknown_target(tmp_path):
    rc = cli.run(["--target", "missing", "--store", str(tmp_path / "o.jsonl")])
    assert rc == 2
