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
assert payload["traces"][0]["name"] == "python-smoke-chat"
assert payload["traces"][0]["project_id"] == "real-python"

print("python-fastapi-smoke ok")
