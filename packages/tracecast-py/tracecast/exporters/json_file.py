import json
import asyncio
from pathlib import Path
from typing import Iterable, List, Optional, Set
from .base import BaseExporter
from ._eval_store import filter_sort_evals, filter_sort_scores
from ..models.trace import Trace


def _filter_dict(doc: dict, include: Optional[Set[str]], exclude: Optional[Set[str]]) -> dict:
    if include is not None:
        return {k: v for k, v in doc.items() if k in include}
    if exclude is not None:
        return {k: v for k, v in doc.items() if k not in exclude}
    return doc


class JsonFileExporter(BaseExporter):

    def __init__(
        self,
        path: str = "./traces.jsonl",
        include_fields: Optional[Iterable[str]] = None,
        exclude_fields: Optional[Iterable[str]] = None,
    ):
        self.path = Path(path)
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._eval_path = Path(str(self.path) + ".evals.jsonl")
        self._score_path = Path(str(self.path) + ".scores.jsonl")
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None

    def export(self, trace: Trace) -> None:
        doc = _filter_dict(trace.to_dict(), self._include, self._exclude)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc, default=str) + "\n")

    async def aexport(self, trace: Trace) -> None:
        await asyncio.to_thread(self.export, trace)

    def _read_evals(self) -> List[dict]:
        if not self._eval_path.exists():
            return []
        rows = []
        for line in self._eval_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def export_eval(self, run) -> None:
        doc = run.to_dict()
        rows = [e for e in self._read_evals() if e.get("run_id") != doc.get("run_id")]
        rows.append(doc)
        with self._eval_path.open("w", encoding="utf-8") as f:
            for e in rows:
                f.write(json.dumps(e, default=str) + "\n")

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> List[dict]:
        return filter_sort_evals(
            self._read_evals(), project_id=project_id, dataset_name=dataset_name,
            from_dt=from_dt, to_dt=to_dt, limit=limit, offset=offset,
        )

    def get_eval(self, run_id: str) -> Optional[dict]:
        return next((e for e in self._read_evals() if e.get("run_id") == run_id), None)

    def _read_scores(self) -> List[dict]:
        if not self._score_path.exists():
            return []
        rows = []
        for line in self._score_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def export_score(self, score) -> None:
        doc = score.to_dict()
        rows = [s for s in self._read_scores() if s.get("score_id") != doc.get("score_id")]
        rows.append(doc)
        with self._score_path.open("w", encoding="utf-8") as f:
            for s in rows:
                f.write(json.dumps(s, default=str) + "\n")

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> List[dict]:
        return filter_sort_scores(
            self._read_scores(), trace_id=trace_id, name=name,
            from_dt=from_dt, to_dt=to_dt, limit=limit, offset=offset,
        )
