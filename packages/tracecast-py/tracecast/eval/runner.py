import inspect
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Union

from ..core.tracer import Tracer
from .dataset import GoldenCase, GoldenDataset, load_dataset
from .decorator import EvalTarget, get_target
from .judge import LLMJudge
from .metrics import get_metric
from .models import EvalCase, EvalRun, TurnResult
from .scorers import run_scorer


def _normalize_criteria(raw, base_scorers):
    """Split raw criteria (dicts or metric-name strings) into LLM judge
    criteria and an extended scorers list (heuristic metrics appended)."""
    criteria = []
    scorers = list(base_scorers)
    for entry in raw or []:
        if isinstance(entry, str):
            metric = get_metric(entry)
            if metric is None:
                raise ValueError(f"unknown metric: {entry}")
            if metric.kind == "llm":
                criteria.append({"name": metric.name, "description": metric.description,
                                 "needs_context": metric.needs_context})
            elif entry not in scorers:
                scorers.append(entry)
        elif isinstance(entry, dict):
            criteria.append(entry)
    return criteria, scorers

_HISTORY_PARAMS = {"messages", "history", "conversation"}


def _wants_history(fn) -> bool:
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return bool(positional) and positional[0].name in _HISTORY_PARAMS


def _call_target(fn, history: list, last_user: Optional[str]):
    if _wants_history(fn):
        return fn(history)
    return fn(last_user)


def _resolve_target(target: Union[EvalTarget, str]) -> EvalTarget:
    if isinstance(target, EvalTarget):
        return target
    resolved = get_target(target)
    if resolved is None:
        raise ValueError(f"eval target not registered: {target}")
    return resolved


def _run_case(case: GoldenCase, target, judge, criteria, scorers, threshold, tracer, run_name) -> EvalCase:
    result = EvalCase(case_id=case.case_id, metadata=case.metadata)
    judge_acc = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
    try:
        with tracer.trace(name=f"eval:{run_name}:{case.case_id}", project_id=getattr(target, "project_id", None)) as trace:
            result.trace_id = trace.trace_id
            history: list = []
            turn_index = 0
            for turn in case.turns:
                if turn.role != "assistant":
                    if turn.content is not None:
                        history.append({"role": turn.role, "content": turn.content})
                    continue
                last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
                output = _call_target(target.fn, history, last_user)
                output = output if isinstance(output, str) else str(output)

                turn_context = turn.context or case.context
                scores = [run_scorer(name, output, turn.expected) for name in scorers]
                if criteria:
                    judge_kwargs = dict(input=last_user, output=output,
                                        expected=turn.expected, criteria=criteria)
                    if turn_context:
                        judge_kwargs["context"] = turn_context
                    jr = judge.score(**judge_kwargs)
                    scores.extend(jr.scores)
                    judge_acc["tokens_in"] += jr.tokens_in
                    judge_acc["tokens_out"] += jr.tokens_out
                    judge_acc["cost"] += jr.cost_usd

                tr = TurnResult(index=turn_index, role="assistant", input=last_user,
                                output=output, expected=turn.expected, scores=scores)
                tr.compute(threshold)
                result.turns.append(tr)
                history.append({"role": "assistant", "content": output})
                turn_index += 1
    except Exception as exc:
        result.status = "error"
        result.error = str(exc)

    result.compute(threshold)
    result.metadata["_judge"] = judge_acc
    return result


def run_evaluation(
    target: Union[EvalTarget, str],
    *,
    exporters: Optional[list] = None,
    dataset: Optional[Union[str, GoldenDataset]] = None,
    judge=None,
    tracer: Optional[Tracer] = None,
    project_id: Optional[str] = None,
) -> EvalRun:
    target = _resolve_target(target)
    exporters = exporters or []
    tracer = tracer or Tracer(exporters=exporters)

    if dataset is None:
        dataset = target.datasets[0]
    ds = load_dataset(dataset) if isinstance(dataset, str) else dataset

    raw_criteria = target.criteria or ds.criteria
    criteria, scorers = _normalize_criteria(raw_criteria, target.scorers)
    threshold = target.threshold if target.threshold is not None else (ds.threshold or 0.7)
    judge_model = target.judge_model or "gpt-4o-mini"
    if judge is None and criteria:
        judge = LLMJudge(model=judge_model)

    run = EvalRun(
        run_id=str(uuid.uuid4()),
        name=target.name,
        started_at=datetime.now(timezone.utc),
        dataset_name=ds.name,
        dataset_path=ds.path,
        target=target.name,
        project_id=project_id or target.project_id,
        judge_model=judge_model if criteria else None,
        criteria=[c["name"] for c in criteria],
        threshold=threshold,
    )

    for case in ds.cases:
        result = _run_case(case, target, judge, criteria, scorers, threshold, tracer, run.name)
        acc = result.metadata.pop("_judge", {})
        run.judge_tokens += acc.get("tokens_in", 0) + acc.get("tokens_out", 0)
        run.judge_cost_usd += acc.get("cost", 0.0)
        run.cases.append(result)

    run.finished_at = datetime.now(timezone.utc)
    run.finalize()

    for exporter in exporters:
        if callable(getattr(exporter, "export_eval", None)):
            try:
                exporter.export_eval(run)
            except Exception as exc:
                from ..core.logger import _logger
                _logger.error("TraceCast: export_eval failed for run %s: %s", run.run_id, exc, exc_info=True)
    return run
