from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from tracecast.exporters.mongo import MongoExporter
from tracecast.models.trace import Trace


def _make_trace():
    t = Trace(trace_id="t-mongo", name="test", started_at=datetime.now(timezone.utc))
    t.finished_at = datetime.now(timezone.utc)
    t._finalize()
    return t


def test_export_chama_insert_one():
    with patch("tracecast.exporters.mongo.MongoClient") as MockClient:
        mock_col = MagicMock()
        MockClient.return_value.__getitem__.return_value.__getitem__.return_value = mock_col
        exporter = MongoExporter(uri="mongodb://localhost:27017")
        exporter.export(_make_trace())
        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["trace_id"] == "t-mongo"
        assert "exported_at" in doc
