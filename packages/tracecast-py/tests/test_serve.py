import base64

import pytest

from tracecast.serve import build_exporter_from_dsn, _parse_auth

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from tracecast.dashboard.standalone import _build_app
from tracecast.dashboard.reader import TraceReader
from tracecast.exporters.dict_exporter import DictExporter


def test_build_exporter_file_dsn(tmp_path):
    from tracecast.exporters.json_file import JsonFileExporter
    exp = build_exporter_from_dsn(str(tmp_path / "t.jsonl"))
    assert isinstance(exp, JsonFileExporter)


def test_build_exporter_file_scheme(tmp_path):
    from tracecast.exporters.json_file import JsonFileExporter
    exp = build_exporter_from_dsn(f"file://{tmp_path}/t.jsonl")
    assert isinstance(exp, JsonFileExporter)


def test_build_exporter_unsupported():
    with pytest.raises(ValueError):
        build_exporter_from_dsn("redis://localhost")


def test_parse_auth():
    assert _parse_auth("user:pass") == ("user", "pass")
    assert _parse_auth(None) is None
    assert _parse_auth("noseparator") is None


def test_standalone_basic_auth_blocks_and_allows():
    reader = TraceReader([DictExporter()])
    app = _build_app(reader, prefix="/tc", auth=("admin", "secret"))
    client = TestClient(app)

    assert client.get("/tc/api/health").status_code == 401

    token = base64.b64encode(b"admin:secret").decode()
    ok = client.get("/tc/api/health", headers={"Authorization": f"Basic {token}"})
    assert ok.status_code == 200


def test_standalone_no_auth_open():
    reader = TraceReader([DictExporter()])
    app = _build_app(reader, prefix="/tc")
    client = TestClient(app)
    assert client.get("/tc/api/health").status_code == 200
