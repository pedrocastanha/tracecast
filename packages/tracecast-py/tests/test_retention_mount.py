from unittest.mock import MagicMock, patch

import pytest

from tracecast import Tracer

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_mongo_exporter():
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    mock_snapshots = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__ = MagicMock(return_value=mock_db)

    with patch("pymongo.MongoClient", return_value=mock_client_instance):
        from tracecast.exporters.mongo import MongoExporter
        exporter = MongoExporter(uri="mongodb://localhost:27017")
        exporter._collection = mock_col
        exporter.col = mock_col
        exporter._snapshots = mock_snapshots
    return exporter


def test_mount_with_retention_days_serves_requests():
    exporter = _make_mongo_exporter()
    tracer = Tracer(exporters=[exporter], retention_days=7)
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    client = TestClient(app)

    resp = client.get("/tc/api/health")

    assert resp.status_code == 200


def test_mount_retention_days_via_mount_kwarg_serves_requests():
    exporter = _make_mongo_exporter()
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc", retention_days=3)
    client = TestClient(app)

    resp = client.get("/tc/api/traces")

    assert resp.status_code == 200
