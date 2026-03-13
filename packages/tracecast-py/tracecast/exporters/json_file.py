import json
import asyncio
from pathlib import Path
from typing import Iterable, Optional, Set
from .base import BaseExporter
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
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None

    def export(self, trace: Trace) -> None:
        doc = _filter_dict(trace.to_dict(), self._include, self._exclude)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc, default=str) + "\n")

    async def aexport(self, trace: Trace) -> None:
        await asyncio.to_thread(self.export, trace)
