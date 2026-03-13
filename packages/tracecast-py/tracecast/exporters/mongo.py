from datetime import datetime, timezone
from typing import Iterable, Optional, Set
from pymongo import MongoClient
from .base import BaseExporter
from ..models.trace import Trace


def _filter_doc(doc: dict, include: Optional[Set[str]], exclude: Optional[Set[str]]) -> dict:
    if include is not None:
        return {k: v for k, v in doc.items() if k in include}
    if exclude is not None:
        return {k: v for k, v in doc.items() if k not in exclude}
    return doc


class MongoExporter(BaseExporter):

    def __init__(
        self,
        uri: str,
        db: str = "tracecast",
        collection: str = "traces",
        include_fields: Optional[Iterable[str]] = None,
        exclude_fields: Optional[Iterable[str]] = None,
    ):
        self.col = MongoClient(uri)[db][collection]
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None

    def export(self, trace: Trace) -> None:
        doc = trace.to_dict()
        doc["exported_at"] = datetime.now(timezone.utc)
        doc = _filter_doc(doc, self._include, self._exclude)
        self.col.insert_one(doc)
