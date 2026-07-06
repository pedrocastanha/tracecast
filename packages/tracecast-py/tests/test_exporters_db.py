import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from tracecast import Tracer
from tracecast.models.span import Span, SpanType
from tracecast.models.trace import Trace

def make_trace(**kwargs) -> Trace:
    t = Trace(
        trace_id=str(uuid.uuid4()),
        name="test-trace",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        **kwargs,
    )
    t._finalize()
    return t


class TestMongoExporter:
    def _make_exporter(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_client_instance = MagicMock()
        mock_client_instance.__getitem__ = MagicMock(return_value=mock_db)

        with patch("pymongo.MongoClient", return_value=mock_client_instance):
            from tracecast.exporters.mongo import MongoExporter
            exporter = MongoExporter(
                uri="mongodb://localhost:27017",
                db="tracecast_test",
                collection="traces",
            )
            exporter._collection = mock_col
            exporter.col = mock_col
        return exporter, mock_col

    @staticmethod
    def _replaced_doc(mock_col):
        return mock_col.replace_one.call_args[0][1]

    def test_export_faz_upsert(self):
        exporter, mock_col = self._make_exporter()
        trace = make_trace(user_id="u1")

        exporter.export(trace)

        mock_col.replace_one.assert_called_once()
        assert mock_col.replace_one.call_args[0][0] == {"trace_id": trace.trace_id}
        assert mock_col.replace_one.call_args.kwargs.get("upsert") is True
        doc = self._replaced_doc(mock_col)
        assert doc["trace_id"] == trace.trace_id
        assert doc["user_id"] == "u1"
        assert "exported_at" in doc

    def test_exported_at_is_datetime(self):
        exporter, mock_col = self._make_exporter()
        trace = make_trace()
        exporter.export(trace)
        doc = self._replaced_doc(mock_col)
        assert isinstance(doc["exported_at"], datetime)

    def test_export_inclui_spans(self):
        exporter, mock_col = self._make_exporter()

        trace = make_trace(user_id="u2")
        now = datetime.now(timezone.utc)
        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llm:gpt-4o",
            model="gpt-4o",
            started_at=now,
            finished_at=now,
            tokens_in=100,
            tokens_out=50,
        )
        span.cost_usd = 0.0025
        trace.spans.append(span)
        trace._finalize()

        exporter.export(trace)
        doc = self._replaced_doc(mock_col)
        assert len(doc["spans"]) == 1
        assert doc["spans"][0]["model"] == "gpt-4o"
        assert doc["total_tokens"] == 150

    def test_query_get_count_pushdown(self):
        exporter, mock_col = self._make_exporter()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.skip.return_value = cursor
        cursor.limit.return_value = [{"trace_id": "x"}]
        mock_col.find.return_value = cursor
        mock_col.count_documents.return_value = 7
        mock_col.find_one.return_value = {"trace_id": "x"}

        rows = exporter.query(project_id="p1", limit=10, offset=20, sort_by="cost", order="asc")
        assert rows == [{"trace_id": "x"}]
        assert mock_col.find.call_args[0][0]["project_id"] == "p1"
        cursor.skip.assert_called_with(20)
        cursor.limit.assert_called_with(10)

        assert exporter.count(project_id="p1") == 7
        assert exporter.get("x") == {"trace_id": "x"}

    def test_integra_com_tracer(self):
        mock_col = MagicMock()

        with patch("pymongo.MongoClient") as MockClient:
            instance = MockClient.return_value
            instance.__getitem__.return_value.__getitem__.return_value = mock_col

            from tracecast.exporters.mongo import MongoExporter
            exporter = MongoExporter("mongodb://localhost:27017")
            exporter._collection = mock_col
            exporter.col = mock_col

            tracer = Tracer(exporters=[exporter])
            with tracer.trace("mongo-integration", project_id="proj-1") as trace:
                now = datetime.now(timezone.utc)
                span = Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name="llm:claude-sonnet-4-6",
                    model="claude-sonnet-4-6",
                    started_at=now,
                    finished_at=now,
                    tokens_in=200,
                    tokens_out=100,
                )
                span.cost_usd = 0.003
                trace.spans.append(span)

        mock_col.replace_one.assert_called_once()
        doc = mock_col.replace_one.call_args[0][1]
        assert doc["project_id"] == "proj-1"
        assert doc["model"] == "claude-sonnet-4-6"
        assert doc["total_tokens"] == 300
        assert doc["cost_usd"] > 0

    def test_compute_daily_snapshot_upserts_per_project(self):
        from datetime import date
        exporter, mock_col = self._make_exporter()
        mock_snapshots = MagicMock()
        exporter._snapshots = mock_snapshots
        mock_col.aggregate.return_value = [
            {
                "_id": "p1", "project_name": "proj-one", "trace_count": 3,
                "total_tokens_in": 100, "total_tokens_out": 50,
                "total_tokens_in_cached": 10, "total_cost_usd": 0.05,
                "total_latency_ms": 900,
            },
            {
                "_id": None, "project_name": None, "trace_count": 1,
                "total_tokens_in": 5, "total_tokens_out": 2,
                "total_tokens_in_cached": 0, "total_cost_usd": 0.001,
                "total_latency_ms": 100,
            },
        ]

        day = date(2026, 6, 1)
        count = exporter.compute_daily_snapshot(day)

        assert count == 2
        match = mock_col.aggregate.call_args[0][0][0]["$match"]
        assert match["started_at"]["$gte"] == "2026-06-01T00:00:00+00:00"
        assert match["started_at"]["$lt"] == "2026-06-02T00:00:00+00:00"

        calls = mock_snapshots.replace_one.call_args_list
        assert len(calls) == 2
        filter0, doc0 = calls[0][0]
        assert filter0 == {"date": "2026-06-01", "project_id": "p1"}
        assert doc0["trace_count"] == 3
        assert doc0["total_cost_usd"] == 0.05
        assert calls[0].kwargs.get("upsert") is True

    def test_purge_traces_before_uses_isoformat_cutoff(self):
        exporter, mock_col = self._make_exporter()
        mock_col.delete_many.return_value = MagicMock(deleted_count=42)
        cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)

        deleted = exporter.purge_traces_before(cutoff)

        assert deleted == 42
        filt = mock_col.delete_many.call_args[0][0]
        assert filt["started_at"]["$lt"] == cutoff.isoformat()
        assert isinstance(filt["started_at"]["$lt"], str)

    def test_query_snapshots_filters_by_date_range_and_project(self):
        from datetime import date
        exporter, _ = self._make_exporter()
        mock_snapshots = MagicMock()
        mock_snapshots.find.return_value = [{"date": "2026-06-01", "trace_count": 3}]
        exporter._snapshots = mock_snapshots

        rows = exporter.query_snapshots(
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 7), project_id="p1",
        )

        assert rows == [{"date": "2026-06-01", "trace_count": 3}]
        match = mock_snapshots.find.call_args[0][0]
        assert match["date"] == {"$gte": "2026-06-01", "$lte": "2026-06-07"}
        assert match["project_id"] == "p1"

    def test_oldest_trace_date_parses_iso_string(self):
        exporter, mock_col = self._make_exporter()
        mock_col.find_one.return_value = {"started_at": "2026-06-01T12:00:00+00:00"}

        from datetime import date
        assert exporter.oldest_trace_date() == date(2026, 6, 1)

    def test_oldest_trace_date_none_when_empty(self):
        exporter, mock_col = self._make_exporter()
        mock_col.find_one.return_value = None
        assert exporter.oldest_trace_date() is None

    def test_mongo_nao_instalado_lanca_import_error(self):
        with patch.dict("sys.modules", {"pymongo": None}):
            import importlib
            import tracecast.exporters.mongo as _m
            with pytest.raises((ImportError, Exception)):
                importlib.reload(_m)
                from tracecast.exporters.mongo import MongoExporter
                MongoExporter("mongodb://localhost:27017")


class TestPostgresExporter:
    def _make_exporter(self):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.closed = False

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_psycopg2.extras.Json = lambda d: d

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": mock_psycopg2.extras}):
            from tracecast.exporters.postgres import PostgresExporter
            exporter = PostgresExporter(dsn="postgresql://user:pass@localhost/db")
            exporter._conn = mock_conn
            exporter._psycopg2 = mock_psycopg2
            exporter._extras = mock_psycopg2.extras

        return exporter, mock_cursor, mock_conn

    def test_export_executa_insert(self):
        exporter, mock_cursor, _ = self._make_exporter()
        trace = make_trace(user_id="u3", project_id="proj-pg")

        exporter.export(trace)

        mock_cursor.execute.assert_called()
        sql_calls = [str(c.args[0]) for c in mock_cursor.execute.call_args_list]
        assert any("INSERT" in s.upper() for s in sql_calls)

    def test_export_inclui_on_conflict(self):
        exporter, mock_cursor, _ = self._make_exporter()
        trace = make_trace()
        exporter.export(trace)
        last_call_sql = str(mock_cursor.execute.call_args[0][0])
        assert "ON CONFLICT" in last_call_sql.upper()

    def test_export_pass_row_com_trace_id(self):
        exporter, mock_cursor, _ = self._make_exporter()
        trace = make_trace(user_id="alice")

        exporter.export(trace)

        row = mock_cursor.execute.call_args[0][1]
        assert row["trace_id"] == trace.trace_id
        assert row["user_id"] == "alice"

    def test_integra_com_tracer(self):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.closed = False

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_psycopg2.extras.Json = lambda d: d

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": mock_psycopg2.extras}):
            from tracecast.exporters.postgres import PostgresExporter
            exporter = PostgresExporter(dsn="postgresql://user:pass@localhost/db")
            exporter._conn = mock_conn
            exporter._psycopg2 = mock_psycopg2
            exporter._extras = mock_psycopg2.extras

            tracer = Tracer(exporters=[exporter])
            with tracer.trace("pg-integration", session_id="sess-pg") as trace:
                now = datetime.now(timezone.utc)
                span = Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name="llm:gpt-4o-mini",
                    model="gpt-4o-mini",
                    started_at=now,
                    finished_at=now,
                    tokens_in=300,
                    tokens_out=150,
                )
                span.cost_usd = 0.00015 + 0.00009
                trace.spans.append(span)

        calls_sql = [str(c.args[0]) for c in mock_cursor.execute.call_args_list]
        assert any("INSERT" in s.upper() for s in calls_sql)
        row = mock_cursor.execute.call_args[0][1]
        assert row["session_id"] == "sess-pg"
        assert row["total_tokens"] == 450

    def test_close_fecha_conexao(self):
        exporter, _, mock_conn = self._make_exporter()
        exporter.close()
        mock_conn.close.assert_called_once()

    def test_context_manager(self):
        exporter, _, mock_conn = self._make_exporter()
        with exporter:
            pass
        mock_conn.close.assert_called_once()

    def test_psycopg2_nao_instalado_lanca_import_error(self):
        with patch.dict("sys.modules", {"psycopg2": None, "psycopg2.extras": None}):
            from tracecast.exporters import postgres as pg_mod
            import importlib
            with pytest.raises((ImportError, Exception)):
                importlib.reload(pg_mod)
                pg_mod.PostgresExporter("postgresql://localhost/db")
