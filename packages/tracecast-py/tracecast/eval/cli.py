import argparse
import importlib
import sys
from typing import List, Optional

from .decorator import get_target
from .judge import LLMJudge
from .runner import run_evaluation


def _resolve_target_name(target: str) -> str:
    if ":" in target:
        module, name = target.rsplit(":", 1)
        importlib.import_module(module)
        return name
    return target


def run(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="tracecast-eval", description="Run a golden-dataset evaluation")
    parser.add_argument("--target", required=True, help="registered name or module:name")
    parser.add_argument("--store", required=True, help="exporter DSN (mongodb://, postgresql://, file://, .jsonl)")
    parser.add_argument("--dataset", help="override golden dataset path")
    parser.add_argument("--judge-model", help="LLM judge model")
    parser.add_argument("--db", help="Mongo db name")
    parser.add_argument("--collection", help="Mongo collection")
    parser.add_argument("--table", help="Postgres table")
    parser.add_argument("--project", help="project_id override")
    args = parser.parse_args(argv)

    name = _resolve_target_name(args.target)
    target = get_target(name)
    if target is None:
        print(f"error: target not registered: {name}", file=sys.stderr)
        return 2

    from ..serve import build_exporter_from_dsn
    exporter = build_exporter_from_dsn(args.store, db=args.db, collection=args.collection, table=args.table)
    judge = LLMJudge(model=args.judge_model) if args.judge_model else None

    run_obj = run_evaluation(
        name, exporters=[exporter], dataset=args.dataset, judge=judge, project_id=args.project,
    )

    print(
        f"[{run_obj.name}] dataset={run_obj.dataset_name} "
        f"cases={run_obj.total_cases} passed={run_obj.passed} failed={run_obj.failed} "
        f"pass_rate={run_obj.pass_rate:.2%} avg_score={run_obj.avg_score:.3f} "
        f"judge_cost=${run_obj.judge_cost_usd:.4f} run_id={run_obj.run_id}"
    )
    return 0 if run_obj.pass_rate >= run_obj.threshold else 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
