from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from tracecast.eval.models import EvalRun, EvalCase, TurnResult, CriterionScore
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.exporters.json_file import JsonFileExporter


def _run(run_id="r1", project_id="p1", dataset="d1"):
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    run = EvalRun(run_id=run_id, name="bot", started_at=base, project_id=project_id,
                  dataset_name=dataset, criteria=["a"], threshold=0.5)
    c = EvalCase(case_id="c1", trace_id="t1")
    c.turns = [TurnResult(index=0, role="assistant", output="o", expected="e",
                          scores=[CriterionScore(name="a", score=1.0)])]
    c.turns[0].compute(0.5)
    c.compute(0.5)
    run.cases = [c]
    run.finished_at = base
    run.finalize()
    return run


def test_dict_store_roundtrip_and_upsert():
    exp = DictExporter()
    exp.export_eval(_run())
    exp.export_eval(_run())
    assert len(exp.evals) == 1
    got = exp.get_eval("r1")
    assert got["run_id"] == "r1"
    assert got["cases"][0]["trace_id"] == "t1"


def test_dict_query_filters():
    exp = DictExporter()
    exp.export_eval(_run("r1", "p1", "d1"))
    exp.export_eval(_run("r2", "p2", "d2"))
    assert {e["run_id"] for e in exp.query_evals(project_id="p1")} == {"r1"}
    assert {e["run_id"] for e in exp.query_evals(dataset_name="d2")} == {"r2"}
    assert len(exp.query_evals()) == 2


def test_jsonfile_store_roundtrip(tmp_path):
    exp = JsonFileExporter(path=str(tmp_path / "t.jsonl"))
    exp.export_eval(_run("r1"))
    exp.export_eval(_run("r1"))
    assert len(exp.query_evals()) == 1
    assert exp.get_eval("r1")["run_id"] == "r1"


def test_mongo_export_eval_upsert():
    with patch("tracecast.exporters.mongo.MongoClient") as MockClient:
        eval_col = MagicMock()
        db = MagicMock()
        db.__getitem__.side_effect = lambda name: eval_col
        MockClient.return_value.__getitem__.return_value = db
        from tracecast.exporters.mongo import MongoExporter
        exp = MongoExporter("mongodb://localhost:27017")
        exp._eval_collection = eval_col
        exp.export_eval(_run("r1"))
        eval_col.replace_one.assert_called_once()
        assert eval_col.replace_one.call_args[0][0] == {"run_id": "r1"}
        assert eval_col.replace_one.call_args.kwargs.get("upsert") is True
