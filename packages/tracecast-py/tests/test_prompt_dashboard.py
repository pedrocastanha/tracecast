import pytest

from tracecast import Tracer
from tracecast.prompts import create_prompt
from tracecast.prompts.client import clear_cache
from tracecast.exporters.dict_exporter import DictExporter

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(exporter):
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    return TestClient(app)


def test_list_and_detail_prompts():
    clear_cache()
    exp = DictExporter()
    create_prompt("greeting", "v1", labels=["production"], exporters=[exp])
    create_prompt("greeting", "v2", exporters=[exp])
    create_prompt("farewell", "bye", exporters=[exp])
    client = _client(exp)

    listing = client.get("/tc/api/prompts")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2  # 2 distinct names
    names = {p["name"] for p in body["prompts"]}
    assert names == {"greeting", "farewell"}

    detail = client.get("/tc/api/prompts/greeting")
    assert detail.status_code == 200
    versions = detail.json()["versions"]
    assert [v["version"] for v in versions] == [1, 2]


def test_detail_unknown_prompt_404():
    exp = DictExporter()
    client = _client(exp)
    assert client.get("/tc/api/prompts/ghost").status_code == 404


def test_prompt_reader_groups_versions():
    from tracecast.dashboard.prompt_reader import PromptReader
    clear_cache()
    exp = DictExporter()
    create_prompt("p", "v1", exporters=[exp])
    create_prompt("p", "v2", exporters=[exp])
    reader = PromptReader([exp])
    summaries = reader.list_prompts()
    assert summaries[0]["name"] == "p"
    assert summaries[0]["latest_version"] == 2
