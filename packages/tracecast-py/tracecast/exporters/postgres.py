import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
from .base import BaseExporter
from ..models.trace import Trace

_ALL_COLUMNS: List[str] = [
    "trace_id",
    "name",
    "session_id",
    "user_id",
    "project_id",
    "model",
    "total_tokens_in",
    "total_tokens_out",
    "total_tokens",
    "cost_usd",
    "latency_ms",
    "tools_used",
    "spans",
    "metadata",
    "started_at",
    "finished_at",
    "exported_at",
]

_COLUMN_DEFS: Dict[str, str] = {
    "trace_id":         "TEXT        NOT NULL",
    "name":             "TEXT        NOT NULL",
    "session_id":       "TEXT",
    "user_id":          "TEXT",
    "project_id":       "TEXT",
    "model":            "TEXT",
    "total_tokens_in":  "INTEGER     DEFAULT 0",
    "total_tokens_out": "INTEGER     DEFAULT 0",
    "total_tokens":     "INTEGER     DEFAULT 0",
    "cost_usd":         "DOUBLE PRECISION DEFAULT 0",
    "latency_ms":       "INTEGER",
    "tools_used":       "JSONB       DEFAULT '{}'",
    "spans":            "JSONB       DEFAULT '[]'",
    "metadata":         "JSONB       DEFAULT '{}'",
    "started_at":       "TIMESTAMPTZ NOT NULL",
    "finished_at":      "TIMESTAMPTZ",
    "exported_at":      "TIMESTAMPTZ NOT NULL",
}

_REQUIRED_COLUMNS: Set[str] = {"trace_id", "started_at", "exported_at"}

_JSONB_COLUMNS: Set[str] = {"tools_used", "spans", "metadata"}


def _build_create_sql(table: str, columns: List[str]) -> str:
    col_parts = ["id BIGSERIAL PRIMARY KEY"]
    for col in columns:
        col_parts.append(f"    {col} {_COLUMN_DEFS[col]}")
    if "trace_id" in columns:
        col_parts.append(f"    CONSTRAINT {table}_trace_id_unique UNIQUE (trace_id)")
    return f"CREATE TABLE IF NOT EXISTS {table} (\n" + ",\n".join(col_parts) + "\n);"


def _build_insert_sql(table: str, columns: List[str]) -> str:
    update_cols = [c for c in columns if c not in ("trace_id", "started_at")]
    placeholders = ", ".join(f"%({c})s" for c in columns)
    col_list = ", ".join(columns)
    set_clause = ",\n    ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    return (
        f"INSERT INTO {table} ({col_list})\n"
        f"VALUES ({placeholders})\n"
        f"ON CONFLICT (trace_id) DO UPDATE SET\n    {set_clause};"
    )


class PostgresExporter(BaseExporter):

    def __init__(
        self,
        dsn: str,
        table: str = "traces",
        autocommit: bool = True,
        include_fields: Optional[Iterable[str]] = None,
        exclude_fields: Optional[Iterable[str]] = None,
    ):
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:
            raise ImportError(
                "psycopg2 is required for PostgresExporter. "
                "Install it with: pip install psycopg2-binary"
            ) from exc

        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._dsn = dsn
        self._table = table
        self._autocommit = autocommit
        self._conn = None

        if include_fields is not None:
            chosen = set(include_fields) | _REQUIRED_COLUMNS
            self._columns = [c for c in _ALL_COLUMNS if c in chosen]
        elif exclude_fields is not None:
            excluded = set(exclude_fields) - _REQUIRED_COLUMNS
            self._columns = [c for c in _ALL_COLUMNS if c not in excluded]
        else:
            self._columns = list(_ALL_COLUMNS)

        self._create_sql = _build_create_sql(self._table, self._columns)
        self._insert_sql = _build_insert_sql(self._table, self._columns)
        self._ensure_table()

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg2.connect(self._dsn)
            self._conn.autocommit = self._autocommit
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(self._create_sql)
        if not self._autocommit:
            conn.commit()

    def _build_row(self, doc: dict) -> dict:
        full_row: Dict[str, Any] = {
            "trace_id":         doc["trace_id"],
            "name":             doc["name"],
            "session_id":       doc.get("session_id"),
            "user_id":          doc.get("user_id"),
            "project_id":       doc.get("project_id"),
            "model":            doc.get("model"),
            "total_tokens_in":  doc["total_tokens_in"],
            "total_tokens_out": doc["total_tokens_out"],
            "total_tokens":     doc["total_tokens"],
            "cost_usd":         doc["cost_usd"],
            "latency_ms":       doc.get("latency_ms"),
            "tools_used":       self._extras.Json(doc["tools_used"]),
            "spans":            self._extras.Json(doc["spans"]),
            "metadata":         self._extras.Json(doc["metadata"]),
            "started_at":       doc["started_at"],
            "finished_at":      doc.get("finished_at"),
            "exported_at":      datetime.now(timezone.utc).isoformat(),
        }
        return {k: v for k, v in full_row.items() if k in self._columns}

    def export(self, trace: Trace) -> None:
        doc = trace.to_dict()
        row = self._build_row(doc)
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(self._insert_sql, row)
        if not self._autocommit:
            conn.commit()

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
