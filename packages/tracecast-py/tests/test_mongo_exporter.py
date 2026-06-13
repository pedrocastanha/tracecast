from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from tracecast.exporters.mongo import MongoExporter
from tracecast.models.trace import Trace


def _make_trace():
    t = Trace(trace_id="t-mongo", name="test", started_at=datetime.now(timezone.utc))
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    return t


def test_export_faz_upsert():
    with patch("tracecast.exporters.mongo.MongoClient") as MockClient:
        mock_col = MagicMock()
        MockClient.return_value.__getitem__.return_value.__getitem__.return_value = mock_col
        exporter = MongoExporter(uri="mongodb://localhost:27017")
        exporter.export(_make_trace())
        mock_col.replace_one.assert_called_once()
        flt, doc = mock_col.replace_one.call_args[0][0], mock_col.replace_one.call_args[0][1]
        assert flt == {"trace_id": "t-mongo"}
        assert mock_col.replace_one.call_args.kwargs.get("upsert") is True
        assert doc["trace_id"] == "t-mongo"
        assert "exported_at" in doc


def test_creates_unique_index_on_first_export():
    with patch("tracecast.exporters.mongo.MongoClient") as MockClient:
        mock_col = MagicMock()
        MockClient.return_value.__getitem__.return_value.__getitem__.return_value = mock_col
        exporter = MongoExporter(uri="mongodb://localhost:27017")
        assert mock_col.create_index.call_count == 0
        exporter.export(_make_trace())
        index_targets = [c.args[0] for c in mock_col.create_index.call_args_list]
        assert "trace_id" in index_targets
