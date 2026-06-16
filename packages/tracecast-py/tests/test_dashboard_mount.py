from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def test_fastapi_mount_serves_dashboard_and_trace_api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    exporter = DictExporter()
    tracer = Tracer(exporters=[exporter])

    with tracer.trace("mounted-dashboard-trace", project_id="project-real"):
        pass

    app = FastAPI()
    tracer.mount(app, prefix="/observability")
    client = TestClient(app)

    dashboard = client.get("/observability/")
    traces = client.get("/observability/api/traces")

    assert dashboard.status_code == 200
    assert "TraceCast" in dashboard.text
    assert traces.status_code == 200
    assert traces.json()["traces"][0]["name"] == "mounted-dashboard-trace"
