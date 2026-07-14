from datetime import date, datetime, timedelta, timezone
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


def _build_match(project_id, user_id, session_id, from_dt, to_dt, project_name=None) -> dict:
    match: Dict[str, Any] = {}
    if project_name:
        match["project_name"] = project_name
    if project_id:
        match["project_id"] = project_id
    if user_id:
        match["user_id"] = user_id
    if session_id:
        match["session_id"] = session_id
    if from_dt or to_dt:
        started: Dict[str, Any] = {}
        if from_dt:
            started["$gte"] = from_dt.isoformat()
        if to_dt:
            started["$lte"] = to_dt.isoformat()
        match["started_at"] = started
    return match


class MongoExporter(BaseExporter):

    def __init__(
        self,
        uri: str,
        db: str = "tracecast",
        collection: str = "traces",
        eval_collection: str = "tracecast_evals",
        score_collection: str = "tracecast_scores",
        prompt_collection: str = "tracecast_prompts",
        include_fields: Optional[Iterable[str]] = None,
        exclude_fields: Optional[Iterable[str]] = None,
        timeout_ms: int = 5000,
        snapshot_collection: str = "tracecast_daily_snapshots",
    ):
        self._db = MongoClient(
            uri,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            serverSelectionTimeoutMS=timeout_ms,
        )[db]
        self.col = self._db[collection]
        self._collection = self.col
        self._eval_collection = self._db[eval_collection]
        self._score_collection = self._db[score_collection]
        self._prompt_collection = self._db[prompt_collection]
        self._snapshots = self._db[snapshot_collection]
        self._include: Optional[Set[str]] = set(include_fields) if include_fields is not None else None
        self._exclude: Optional[Set[str]] = set(exclude_fields) if exclude_fields is not None else None
        self._indexed = False

    # List path: keep token/count scalars, drop heavy span payloads.
    _LIST_PROJECTION = {
        "spans.input": 0,
        "spans.output": 0,
        "edges": 0,
    }

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._collection.create_index("trace_id", unique=True)
            self._collection.create_index([("started_at", DESCENDING)])
            self._collection.create_index([("project_id", ASCENDING), ("started_at", DESCENDING)])
            self._collection.create_index([("project_id", ASCENDING), ("total_tokens", DESCENDING)])
            self._collection.create_index("export_status")
            self._snapshots.create_index([("date", ASCENDING), ("project_id", ASCENDING)], unique=True)
        except Exception:
            pass

    def oldest_trace_date(self) -> Optional[date]:
        doc = self._collection.find_one({}, sort=[("started_at", ASCENDING)], projection={"started_at": 1})
        if not doc or not doc.get("started_at"):
            return None
        return datetime.fromisoformat(doc["started_at"]).date()

    def compute_daily_snapshot(self, day: date) -> int:
        self._ensure_indexes()
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        pipeline = [
            {"$match": {"started_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}}},
            {"$group": {
                "_id": "$project_id",
                "project_name": {"$first": "$project_name"},
                "trace_count": {"$sum": 1},
                "total_tokens_in": {"$sum": "$total_tokens_in"},
                "total_tokens_out": {"$sum": "$total_tokens_out"},
                "total_tokens_in_cached": {"$sum": "$total_tokens_in_cached"},
                "total_cost_usd": {"$sum": "$cost_usd"},
                "total_latency_ms": {"$sum": "$latency_ms"},
            }},
        ]
        groups = list(self._collection.aggregate(pipeline))
        for g in groups:
            doc = {
                "date": day.isoformat(),
                "project_id": g["_id"],
                "project_name": g.get("project_name"),
                "trace_count": g["trace_count"],
                "total_tokens_in": g.get("total_tokens_in") or 0,
                "total_tokens_out": g.get("total_tokens_out") or 0,
                "total_tokens_in_cached": g.get("total_tokens_in_cached") or 0,
                "total_cost_usd": g.get("total_cost_usd") or 0.0,
                "total_latency_ms": g.get("total_latency_ms") or 0,
            }
            self._snapshots.replace_one(
                {"date": doc["date"], "project_id": doc["project_id"]}, doc, upsert=True
            )
        return len(groups)

    def purge_traces_before(self, cutoff: datetime) -> int:
        result = self._collection.delete_many({"started_at": {"$lt": cutoff.isoformat()}})
        return result.deleted_count

    def query_snapshots(
        self,
        *,
        from_date: date,
        to_date: date,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> List[dict]:
        match: Dict[str, Any] = {"date": {"$gte": from_date.isoformat(), "$lte": to_date.isoformat()}}
        if project_id:
            match["project_id"] = project_id
        if project_name:
            match["project_name"] = project_name
        return list(self._snapshots.find(match, {"_id": 0}))

    def export(self, trace: Trace) -> None:
        self.export_doc(trace.to_dict())

    def _write_payload(self, payload: dict) -> None:
        """Upsert one doc; on BSON-too-large fall back to token summary."""
        try:
            self._collection.replace_one(
                {"trace_id": payload["trace_id"]}, payload, upsert=True
            )
        except Exception as exc:
            if not self._is_too_large(exc):
                raise
            from ..core.trace_summary import build_trace_summary

            summary = build_trace_summary(payload, exc)
            summary["exported_at"] = datetime.now(timezone.utc)
            self._collection.replace_one(
                {"trace_id": summary["trace_id"]}, summary, upsert=True
            )

    @staticmethod
    def _is_too_large(exc: BaseException) -> bool:
        name = type(exc).__name__
        if name in ("DocumentTooLarge", "BSONError", "InvalidDocument"):
            return True
        msg = str(exc).lower()
        return "too large" in msg or "document too large" in msg or "bson" in msg and "large" in msg

    def export_doc(self, doc: dict) -> None:
        self._ensure_indexes()
        payload = dict(doc)
        payload["exported_at"] = datetime.now(timezone.utc)
        payload = _filter_doc(payload, self._include, self._exclude)
        self._write_payload(payload)

    def export_docs_batch(self, docs: List[dict]) -> None:
        if not docs:
            return
        self._ensure_indexes()
        from pymongo import ReplaceOne

        now = datetime.now(timezone.utc)
        ops = []
        prepared = []
        for doc in docs:
            payload = dict(doc)
            payload["exported_at"] = now
            payload = _filter_doc(payload, self._include, self._exclude)
            prepared.append(payload)
            ops.append(ReplaceOne({"trace_id": payload["trace_id"]}, payload, upsert=True))
        try:
            self._collection.bulk_write(ops, ordered=False)
        except Exception as exc:
            if not self._is_too_large(exc):
                # Partial/other bulk failures: try per-doc so one fat doc
                # does not erase token totals for the rest.
                for payload in prepared:
                    try:
                        self._write_payload(payload)
                    except Exception:
                        raise exc
                return
            for payload in prepared:
                self._write_payload(payload)

    def export_summary(self, summary: dict) -> None:
        self.export_doc(summary)

    def query(
        self,
        *,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "date",
        order: str = "desc",
        light: bool = True,
    ) -> List[dict]:
        match = _build_match(project_id, user_id, session_id, from_dt, to_dt, project_name=project_name)
        direction = DESCENDING if order == "desc" else ASCENDING
        projection = self._LIST_PROJECTION if light else None
        cursor = (
            self._collection.find(match, projection)
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
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        match = _build_match(project_id, user_id, session_id, from_dt, to_dt, project_name=project_name)
        return self._collection.count_documents(match)

    def export_eval(self, run) -> None:
        doc = run.to_dict()
        self._eval_collection.replace_one({"run_id": doc["run_id"]}, doc, upsert=True)

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> List[dict]:
        match: Dict[str, Any] = {}
        if project_id:
            match["project_id"] = project_id
        if dataset_name:
            match["dataset_name"] = dataset_name
        if from_dt or to_dt:
            started: Dict[str, Any] = {}
            if from_dt:
                started["$gte"] = from_dt.isoformat()
            if to_dt:
                started["$lte"] = to_dt.isoformat()
            match["started_at"] = started
        cursor = (
            self._eval_collection.find(match, {"_id": 0})
            .sort("started_at", DESCENDING)
            .skip(max(offset, 0))
            .limit(max(limit, 0))
        )
        return list(cursor)

    def get_eval(self, run_id: str) -> Optional[dict]:
        return self._eval_collection.find_one({"run_id": run_id}, {"_id": 0})

    def export_score(self, score) -> None:
        doc = score.to_dict()
        self._score_collection.replace_one({"score_id": doc["score_id"]}, doc, upsert=True)

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> List[dict]:
        match: Dict[str, Any] = {}
        if trace_id:
            match["trace_id"] = trace_id
        if name:
            match["name"] = name
        if from_dt or to_dt:
            created: Dict[str, Any] = {}
            if from_dt:
                created["$gte"] = from_dt.isoformat()
            if to_dt:
                created["$lte"] = to_dt.isoformat()
            match["created_at"] = created
        cursor = (
            self._score_collection.find(match, {"_id": 0})
            .sort("created_at", ASCENDING)
            .skip(max(offset, 0))
            .limit(max(limit, 0))
        )
        return list(cursor)

    def export_prompt(self, prompt) -> None:
        doc = prompt.to_dict()
        self._prompt_collection.replace_one(
            {"name": doc["name"], "version": doc["version"]}, doc, upsert=True
        )

    def query_prompts(self, *, name=None) -> List[dict]:
        match: Dict[str, Any] = {}
        if name:
            match["name"] = name
        cursor = self._prompt_collection.find(match, {"_id": 0}).sort(
            [("name", ASCENDING), ("version", ASCENDING)]
        )
        return list(cursor)
