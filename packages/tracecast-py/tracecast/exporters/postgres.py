import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
from .base import BaseExporter
from .query import sort_field
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
        eval_table: str = "tracecast_evals",
        score_table: str = "tracecast_scores",
        prompt_table: str = "tracecast_prompts",
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
        self._eval_table = eval_table
        self._score_table = score_table
        self._prompt_table = prompt_table
        self._autocommit = autocommit
        self._conn = None
        self._read_conn = None
        self._read_lock = threading.Lock()

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
        self._ensure_eval_table()
        self._ensure_score_table()
        self._ensure_prompt_table()

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

    def _ensure_eval_table(self) -> None:
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self._eval_table} (\n"
            "    run_id       TEXT PRIMARY KEY,\n"
            "    project_id   TEXT,\n"
            "    dataset_name TEXT,\n"
            "    started_at   TIMESTAMPTZ,\n"
            "    data         JSONB NOT NULL\n"
            ");"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        if not self._autocommit:
            conn.commit()

    def _ensure_score_table(self) -> None:
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self._score_table} (\n"
            "    score_id   TEXT PRIMARY KEY,\n"
            "    trace_id   TEXT NOT NULL,\n"
            "    name       TEXT,\n"
            "    created_at TIMESTAMPTZ,\n"
            "    data       JSONB NOT NULL\n"
            ");\n"
            f"CREATE INDEX IF NOT EXISTS {self._score_table}_trace_idx "
            f"ON {self._score_table} (trace_id);"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        if not self._autocommit:
            conn.commit()

    def _ensure_prompt_table(self) -> None:
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self._prompt_table} (\n"
            "    name       TEXT NOT NULL,\n"
            "    version    INTEGER NOT NULL,\n"
            "    data       JSONB NOT NULL,\n"
            "    PRIMARY KEY (name, version)\n"
            ");"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
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

    def _get_read_conn(self):
        if self._read_conn is None or self._read_conn.closed:
            self._read_conn = self._psycopg2.connect(self._dsn)
            self._read_conn.autocommit = True
        return self._read_conn

    def _where(self, project_id, user_id, session_id, from_dt, to_dt):
        clauses: List[str] = []
        params: List[Any] = []
        if project_id:
            clauses.append("project_id = %s")
            params.append(project_id)
        if user_id:
            clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if from_dt:
            clauses.append("started_at >= %s")
            params.append(from_dt)
        if to_dt:
            clauses.append("started_at <= %s")
            params.append(to_dt)
        sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return sql, params

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
        where, params = self._where(project_id, user_id, session_id, from_dt, to_dt)
        direction = "DESC" if order == "desc" else "ASC"
        sql = (
            f'SELECT * FROM "{self._table}"{where} '
            f'ORDER BY {sort_field(sort_by)} {direction} LIMIT %s OFFSET %s'
        )
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(sql, (*params, max(limit, 0), max(offset, 0)))
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def get(self, trace_id: str) -> Optional[dict]:
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(f'SELECT * FROM "{self._table}" WHERE trace_id = %s', (trace_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))

    def count(
        self,
        *,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        where, params = self._where(project_id, user_id, session_id, from_dt, to_dt)
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM "{self._table}"{where}', tuple(params))
                return int(cur.fetchone()[0])

    def export_eval(self, run) -> None:
        doc = run.to_dict()
        row = {
            "run_id":       doc["run_id"],
            "project_id":   doc.get("project_id"),
            "dataset_name": doc.get("dataset_name"),
            "started_at":   doc.get("started_at"),
            "data":         self._extras.Json(doc),
        }
        sql = (
            f"INSERT INTO {self._eval_table} (run_id, project_id, dataset_name, started_at, data)\n"
            "VALUES (%(run_id)s, %(project_id)s, %(dataset_name)s, %(started_at)s, %(data)s)\n"
            "ON CONFLICT (run_id) DO UPDATE SET\n"
            "    project_id = EXCLUDED.project_id,\n"
            "    dataset_name = EXCLUDED.dataset_name,\n"
            "    started_at = EXCLUDED.started_at,\n"
            "    data = EXCLUDED.data;"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, row)
        if not self._autocommit:
            conn.commit()

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if project_id:
            clauses.append("project_id = %s")
            params.append(project_id)
        if dataset_name:
            clauses.append("dataset_name = %s")
            params.append(dataset_name)
        if from_dt:
            clauses.append("started_at >= %s")
            params.append(from_dt)
        if to_dt:
            clauses.append("started_at <= %s")
            params.append(to_dt)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT data FROM {self._eval_table}{where} "
            "ORDER BY started_at DESC NULLS LAST LIMIT %s OFFSET %s"
        )
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(sql, (*params, max(limit, 0), max(offset, 0)))
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def get_eval(self, run_id: str) -> Optional[dict]:
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(f"SELECT data FROM {self._eval_table} WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        return row[0] if row else None

    def export_score(self, score) -> None:
        doc = score.to_dict()
        row = {
            "score_id":   doc["score_id"],
            "trace_id":   doc["trace_id"],
            "name":       doc.get("name"),
            "created_at": doc.get("created_at"),
            "data":       self._extras.Json(doc),
        }
        sql = (
            f"INSERT INTO {self._score_table} (score_id, trace_id, name, created_at, data)\n"
            "VALUES (%(score_id)s, %(trace_id)s, %(name)s, %(created_at)s, %(data)s)\n"
            "ON CONFLICT (score_id) DO UPDATE SET\n"
            "    trace_id = EXCLUDED.trace_id,\n"
            "    name = EXCLUDED.name,\n"
            "    created_at = EXCLUDED.created_at,\n"
            "    data = EXCLUDED.data;"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, row)
        if not self._autocommit:
            conn.commit()

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if trace_id:
            clauses.append("trace_id = %s")
            params.append(trace_id)
        if name:
            clauses.append("name = %s")
            params.append(name)
        if from_dt:
            clauses.append("created_at >= %s")
            params.append(from_dt)
        if to_dt:
            clauses.append("created_at <= %s")
            params.append(to_dt)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT data FROM {self._score_table}{where} "
            "ORDER BY created_at ASC NULLS LAST LIMIT %s OFFSET %s"
        )
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(sql, (*params, max(limit, 0), max(offset, 0)))
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def export_prompt(self, prompt) -> None:
        doc = prompt.to_dict()
        sql = (
            f"INSERT INTO {self._prompt_table} (name, version, data)\n"
            "VALUES (%(name)s, %(version)s, %(data)s)\n"
            "ON CONFLICT (name, version) DO UPDATE SET data = EXCLUDED.data;"
        )
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, {"name": doc["name"], "version": doc["version"],
                              "data": self._extras.Json(doc)})
        if not self._autocommit:
            conn.commit()

    def query_prompts(self, *, name=None) -> List[dict]:
        where = " WHERE name = %s" if name else ""
        params = (name,) if name else ()
        sql = f"SELECT data FROM {self._prompt_table}{where} ORDER BY name ASC, version ASC"
        with self._read_lock:
            conn = self._get_read_conn()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
        if self._read_conn and not self._read_conn.closed:
            self._read_conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
