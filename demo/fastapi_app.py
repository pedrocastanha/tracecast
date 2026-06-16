"""Exemplo real: API FastAPI instrumentada com TraceCast.

Tracing automático por request, dashboard embutido e disparo de evaluation por endpoint.
Roda offline (LLM simulado); use OPENAI_API_KEY + auto_instrument para LLMs reais.

Rodar:
    uvicorn demo.fastapi_app:app --port 8000
    # ou:
    python demo/fastapi_app.py

Endpoints:
    GET  /health
    POST /chat                         {"message": "..."}  -> {"answer", "trace_id"}
    GET  /tracecast                    dashboard embutido (Traces + Graph + Evaluators)
    GET  /tracecast/api/traces
    POST /tracecast/api/evals/run      {"target": "support_bot"} -> dispara eval (embutido)

Storage: env TRACECAST_STORE (default file://./demo/demo_output/api_traces.jsonl).
"""

import os
import pathlib
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "tracecast-py"))

from fastapi import FastAPI
from pydantic import BaseModel

from tracecast import Tracer, trace_cast, trace_span, trace_llm_call, evaluator, set_default_tracer
from tracecast.models.span import SpanType
from tracecast.serve import build_exporter_from_dsn

HERE = pathlib.Path(__file__).parent
OUT = HERE / "demo_output"
OUT.mkdir(exist_ok=True)
DATASETS = HERE / "golden_datasets"

STORE = os.environ.get("TRACECAST_STORE", f"file://{OUT / 'api_traces.jsonl'}")
EXPORTER = build_exporter_from_dsn(
    STORE, db=os.environ.get("TRACECAST_DB"), collection=os.environ.get("TRACECAST_COLLECTION"),
)
TRACER = Tracer(exporters=[EXPORTER], logging=True, log_prefix="api", background_export=True)
set_default_tracer(TRACER)

SUPPORT_KB = {
    "Qual o horario de atendimento?": "Atendemos de segunda a sexta, das 8h as 18h.",
    "Como peco reembolso?": "Voce pode solicitar reembolso em ate 7 dias pela pagina de pedidos.",
    "Qual o prazo de entrega?": "Entrega em 2 dias.",
}


def _fake_llm(prompt: str):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=max(len(prompt.split()), 1), completion_tokens=12,
                              prompt_tokens_details=None),
        choices=[SimpleNamespace(message=SimpleNamespace(content=f"resposta: {prompt}", reasoning_content=None))],
    )


@trace_span(name="guardrail_pii", type=SpanType.TOOL)
def guardrail(text: str) -> str:
    return text.strip()


def run_agent(message: str) -> str:
    safe = guardrail(message)
    if safe in SUPPORT_KB:
        return SUPPORT_KB[safe]
    trace_llm_call(lambda: _fake_llm(safe), provider="openai", model="gpt-4o", input_text=safe)
    return f"resposta: {safe}"


@evaluator(dataset=str(DATASETS / "api_faq.json"), name="support_bot",
           scorers=["similarity"], threshold=0.7, project_id="api")
def support_bot(question: str) -> str:
    return SUPPORT_KB.get(question, "Nao sei responder.")


app = FastAPI(title="TraceCast Demo API")


class ChatIn(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "store": STORE, "dashboard": "/tracecast"}


@app.post("/chat")
@trace_cast(tracer=TRACER, project_id="api")
def chat(body: ChatIn):
    answer = run_agent(body.message)
    trace = Tracer.current()
    return {"answer": answer, "trace_id": trace.trace_id if trace else None}


TRACER.mount(app, prefix="/tracecast")


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), log_level="info")


if __name__ == "__main__":
    main()
