"""Demonstração real de tracing com TraceCast.

Roda um agente LangGraph (classify -> faq | smalltalk) com guardrail e chamada LLM,
captura o fluxo inteiro (nós, arestas, tokens, latência) e exporta para JSONL.
Funciona offline (LLM simulado). Se langgraph não estiver instalado, cai para um
fluxo manual equivalente.

Executar:
    python demo/tracing_demo.py

Visualizar no dashboard:
    TRACECAST_STORE="file://$(pwd)/demo/demo_output/traces.jsonl" tracecast-server
    # http://127.0.0.1:7777/tracecast  ->  Traces  ->  abra um trace  ->  aba Graph
"""

import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "tracecast-py"))

from tracecast import Tracer, trace_cast, trace_span, trace_llm_call, set_default_tracer
from tracecast.models.span import SpanType
from tracecast.exporters import JsonFileExporter
from tracecast.dashboard.reader import TraceReader

OUT = pathlib.Path(__file__).parent / "demo_output"
OUT.mkdir(exist_ok=True)
EXPORTER = JsonFileExporter(str(OUT / "traces.jsonl"))
TRACER = Tracer(exporters=[EXPORTER], logging=True, log_prefix="demo")
set_default_tracer(TRACER)


@trace_span(name="guardrail_pii", type=SpanType.TOOL)
def guardrail(text: str) -> str:
    return text.strip()


def fake_llm(prompt: str):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=max(len(prompt.split()), 1), completion_tokens=8,
                              prompt_tokens_details=None),
        choices=[SimpleNamespace(message=SimpleNamespace(content=f"resposta para: {prompt}",
                                                         reasoning_content=None))],
    )


def _build_langgraph():
    from langgraph.graph import StateGraph, END
    from typing import TypedDict

    class State(TypedDict):
        text: str
        route: str
        answer: str

    def classify(state):
        return {"route": "faq" if "?" in state["text"] else "smalltalk"}

    def faq(state):
        safe = guardrail(state["text"])
        trace_llm_call(lambda: fake_llm(safe), provider="openai", model="gpt-4o", input_text=safe)
        return {"answer": "faq"}

    def smalltalk(state):
        trace_llm_call(lambda: fake_llm(state["text"]), provider="openai", model="gpt-4o-mini",
                       input_text=state["text"])
        return {"answer": "smalltalk"}

    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("faq", faq)
    g.add_node("smalltalk", smalltalk)
    g.set_entry_point("classify")
    g.add_conditional_edges("classify", lambda s: s["route"], {"faq": "faq", "smalltalk": "smalltalk"})
    g.add_edge("faq", END)
    g.add_edge("smalltalk", END)
    return g.compile()


@trace_cast(tracer=TRACER, project_id="demo", user_id="user-1")
def handle(message: str):
    try:
        from tracecast.integrations.langchain import TraceCastCallback
        app = _build_langgraph()
        cb = TraceCastCallback(tracer=TRACER)
        return app.invoke({"text": message}, config={"callbacks": [cb]})
    except Exception:
        safe = guardrail(message)
        trace_llm_call(lambda: fake_llm(safe), provider="openai", model="gpt-4o", input_text=safe)
        return {"answer": "fallback"}


def main():
    handle("Qual o horario de atendimento?")
    handle("oi, tudo bem")

    print("\n--- traces capturados ---")
    for t in TraceReader([EXPORTER]).get_traces():
        print(f"{t.name}  spans={len(t.spans)}  edges={len(t.edges)}  "
              f"tokens={t.total_tokens}  cost=${t.cost_usd:.4f}  latency={t.latency_ms}ms")
        for s in t.spans:
            parent = s.parent_span_id[:8] if s.parent_span_id else "root"
            print(f"    [{s.type.value:5}] {s.name:24} parent={parent} status={s.status.value}")
    print(f"\nExportado para {OUT / 'traces.jsonl'}")


if __name__ == "__main__":
    main()
