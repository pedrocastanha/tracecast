from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
from pymongo import ASCENDING, DESCENDING, MongoClient
from .base import BaseExporter
from .query import sort_field
from ..models.trace import Trace


def _filter_doc(doc: dict, include: Optional[Set[str]], exclude: Optional[Set[str]]) -> dict:
    if include is not None:
        return {k: v for k, v in doc.items() if k in include}
    if exclude is not None:
        return {k: v for k, v in doc.items() if k not in exclude}
    return doc


def _build_match(project_id, user_id, session_id, from_dt, to_dt) -> dict:
    match: Dict[str, Any] = {}
    if project_id:
        match["project_id"] = project_id
    if user_id:
        match["user_id"] = user_id
    if session_id:
        match["session_id"] = session_id
    if from_dt or to_dt:
        started: Dict[str, Any] = {}
        if from_dt:
            started["$gte"] = from_dt
        if to_dt:
            started["$lte"] = to_dt
        match["started_at"] = started
    return match


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
        self._collection = self.col
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._collection.create_index("trace_id", unique=True)
            self._collection.create_index([("started_at", DESCENDING)])
            self._collection.create_index([("project_id", ASCENDING), ("started_at", DESCENDING)])
        except Exception:
            pass

    def export(self, trace: Trace) -> None:
        self._ensure_indexes()
        doc = trace.to_dict()
        doc["exported_at"] = datetime.now(timezone.utc)
        doc = _filter_doc(doc, self._include, self._exclude)
        self._collection.replace_one({"trace_id": doc["trace_id"]}, doc, upsert=True)

    def query(
        self,
        *,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "date",
        order: str = "desc",
    ) -> List[dict]:
        match = _build_match(project_id, user_id, session_id, from_dt, to_dt)
        direction = DESCENDING if order == "desc" else ASCENDING
        cursor = (
            self._collection.find(match)
            .sort(sort_field(sort_by), direction)
            .skip(max(offset, 0))
            .limit(max(limit, 0))
        )
        return list(cursor)

    def get(self, trace_id: str) -> Optional[dict]:
        return self._collection.find_one({"trace_id": trace_id})

    def count(
        self,
        *,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        match = _build_match(project_id, user_id, session_id, from_dt, to_dt)
        return self._collection.count_documents(match)
