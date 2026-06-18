from typing import Any, Callable, Dict, Iterable, List, Optional, Set
from .base import BaseExporter
from ._eval_store import filter_sort_evals, filter_sort_scores
from ..models.trace import Trace


def _filter_dict(doc: dict, include: Optional[Set[str]], exclude: Optional[Set[str]]) -> dict:
    if include is not None:
        return {k: v for k, v in doc.items() if k in include}
    if exclude is not None:
        return {k: v for k, v in doc.items() if k not in exclude}
    return doc


class DictExporter(BaseExporter):

    def __init__(
        self,
        on_trace: Optional[Callable[[Dict[str, Any]], None]] = None,
        include_fields: Optional[Iterable[str]] = None,
        exclude_fields: Optional[Iterable[str]] = None,
    ):
        self._on_trace = on_trace
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None
        self.traces: List[Dict[str, Any]] = []
        self.evals: List[Dict[str, Any]] = []
        self.scores: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []

    def export(self, trace: Trace) -> None:
        doc = _filter_dict(trace.to_dict(), self._include, self._exclude)
        if self._on_trace is not None:
            self._on_trace(doc)
        else:
            self.traces.append(doc)

    def export_eval(self, run) -> None:
        doc = run.to_dict()
        self.evals = [e for e in self.evals if e.get("run_id") != doc.get("run_id")]
        self.evals.append(doc)

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> List[dict]:
        return filter_sort_evals(
            self.evals, project_id=project_id, dataset_name=dataset_name,
            from_dt=from_dt, to_dt=to_dt, limit=limit, offset=offset,
        )

    def get_eval(self, run_id: str) -> Optional[dict]:
        return next((e for e in self.evals if e.get("run_id") == run_id), None)

    def export_score(self, score) -> None:
        doc = score.to_dict()
        self.scores = [s for s in self.scores if s.get("score_id") != doc.get("score_id")]
        self.scores.append(doc)

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> List[dict]:
        return filter_sort_scores(
            self.scores, trace_id=trace_id, name=name,
            from_dt=from_dt, to_dt=to_dt, limit=limit, offset=offset,
        )

    def export_prompt(self, prompt) -> None:
        doc = prompt.to_dict()
        self.prompts = [p for p in self.prompts
                        if not (p.get("name") == doc.get("name") and p.get("version") == doc.get("version"))]
        self.prompts.append(doc)

    def query_prompts(self, *, name=None) -> List[dict]:
        rows = [p for p in self.prompts if name is None or p.get("name") == name]
        return sorted(rows, key=lambda p: (p.get("name", ""), p.get("version", 0)))

    def clear(self) -> None:
        self.traces.clear()
        self.evals.clear()
        self.scores.clear()
        self.prompts.clear()
