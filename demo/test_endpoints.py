"""Teste real (in-process) dos endpoints da API FastAPI de demonstração.

Usa o TestClient do FastAPI — não precisa subir servidor separado. Exercita tracing por
request, leitura via dashboard API, grafo do trace e disparo de evaluation por endpoint.

Executar:
    python demo/test_endpoints.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "tracecast-py"))

from fastapi.testclient import TestClient

from fastapi_app import app, TRACER  # noqa: E402

client = TestClient(app)


def check(label, condition):
    print(f"  [{'OK ' if condition else 'FAIL'}] {label}")
    assert condition, label


def main():
    print("health:")
    r = client.get("/health")
    check("status ok", r.json()["status"] == "ok")

    print("POST /chat (FAQ -> KB):")
    r = client.post("/chat", json={"message": "Qual o horario de atendimento?"})
    body = r.json()
    check("200", r.status_code == 200)
    check("tem trace_id", bool(body["trace_id"]))
    faq_trace = body["trace_id"]

    print("POST /chat (LLM):")
    r = client.post("/chat", json={"message": "me conte uma piada"})
    llm_trace = r.json()["trace_id"]
    check("200 + trace_id", r.status_code == 200 and bool(llm_trace))

    TRACER.flush(timeout=5)  # save é em background; aguarda os writes antes de ler

    print("dashboard: lista de traces:")
    r = client.get("/tracecast/api/traces", params={"project_id": "api"})
    check(">=2 traces", r.json()["total"] >= 2)

    print("dashboard: grafo do trace LLM:")
    g = client.get(f"/tracecast/api/traces/{llm_trace}/graph").json()
    names = [n["name"] for n in g["nodes"]]
    check("guardrail no grafo", any("guardrail" in n for n in names))
    check("span llm no grafo", any(n.startswith("llm:") for n in names))

    print("endpoint de evaluation (embutido):")
    r = client.post("/tracecast/api/evals/run", json={"target": "support_bot"})
    check("200", r.status_code == 200)
    summary = r.json()
    check("rodou casos", summary["total_cases"] >= 1)
    print(f"      pass_rate={summary['pass_rate']:.0%} avg_score={summary['avg_score']:.3f}")

    print("dashboard: lista de evals:")
    r = client.get("/tracecast/api/evals")
    check(">=1 eval run", r.json()["total"] >= 1)

    print("\nTodos os checks passaram.")


if __name__ == "__main__":
    main()
