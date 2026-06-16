from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

chat = client.get("/chat")
assert chat.status_code == 200, chat.text
assert chat.json() == {"reply": "ok"}

dashboard = client.get("/observability/")
assert dashboard.status_code == 200, dashboard.text
assert "TraceCast" in dashboard.text

traces = client.get("/observability/api/traces")
assert traces.status_code == 200, traces.text
payload = traces.json()
trace = payload["traces"][0]
assert trace["name"] == "python-smoke-chat"
assert trace["project_id"] == "real-python"
assert trace["total_tokens_in"] == 90
assert trace["total_tokens_out"] == 30
assert trace["total_tokens_in_cached"] == 20
assert trace["total_tokens"] == 120

print("python-fastapi-smoke ok")
