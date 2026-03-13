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
            exporter.col = mock_col
        return exporter, mock_col

    def test_export_chama_insert_one(self):
        exporter, mock_col = self._make_exporter()
        trace = make_trace(user_id="u1")

        exporter.export(trace)

        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["trace_id"] == trace.trace_id
        assert doc["user_id"] == "u1"
        assert "exported_at" in doc

    def test_exported_at_is_datetime(self):
        exporter, mock_col = self._make_exporter()
        trace = make_trace()
        exporter.export(trace)
        doc = mock_col.insert_one.call_args[0][0]
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
        doc = mock_col.insert_one.call_args[0][0]
        assert len(doc["spans"]) == 1
        assert doc["spans"][0]["model"] == "gpt-4o"
        assert doc["total_tokens"] == 150

    def test_integra_com_tracer(self):
        mock_col = MagicMock()

        with patch("pymongo.MongoClient") as MockClient:
            instance = MockClient.return_value
            instance.__getitem__.return_value.__getitem__.return_value = mock_col

            from tracecast.exporters.mongo import MongoExporter
            exporter = MongoExporter("mongodb://localhost:27017")
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

        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["project_id"] == "proj-1"
        assert doc["model"] == "claude-sonnet-4-6"
        assert doc["total_tokens"] == 300
        assert doc["cost_usd"] > 0

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
