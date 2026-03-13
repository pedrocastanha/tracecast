from typing import Any, Callable, Dict, Iterable, List, Optional, Set
from .base import BaseExporter
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

    def export(self, trace: Trace) -> None:
        doc = _filter_dict(trace.to_dict(), self._include, self._exclude)
        if self._on_trace is not None:
            self._on_trace(doc)
        else:
            self.traces.append(doc)

    def clear(self) -> None:
        self.traces.clear()
