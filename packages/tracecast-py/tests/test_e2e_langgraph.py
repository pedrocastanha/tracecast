from types import SimpleNamespace

import pytest

from tracecast import Tracer, trace_cast, trace_span, trace_llm_call, set_default_tracer
from tracecast.models.span import SpanType, SpanStatus
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.dashboard.reader import TraceReader

langgraph = pytest.importorskip("langgraph")
fastapi = pytest.importorskip("fastapi")
from langgraph.graph import StateGraph, END
from typing import TypedDict
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tracecast.integrations.langchain import TraceCastCallback


class State(TypedDict):
    text: str
    route: str
    answer: str


@trace_span(name="guardrail_pii", type=SpanType.TOOL)
def guardrail(text: str) -> str:
    return text.strip()


def _fake_openai_response():
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4, prompt_tokens_details=None),
        choices=[SimpleNamespace(message=SimpleNamespace(content="resposta A", reasoning_content=None))],
    )


def _build_app():
    def classify(state):
        return {"route": "a" if "hello" in state["text"] else "b"}

    def answer_a(state):
        safe = guardrail(state["text"])
        trace_llm_call(lambda: _fake_openai_response(), provider="openai", model="gpt-4o",
                       input_text=safe)
        return {"answer": "A"}

    def answer_b(state):
        return {"answer": "B"}

    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("answer_a", answer_a)
    g.add_node("answer_b", answer_b)
    g.set_entry_point("classify")
    g.add_conditional_edges("classify", lambda s: s["route"], {"a": "answer_a", "b": "answer_b"})
    g.add_edge("answer_a", END)
    g.add_edge("answer_b", END)
    return g.compile()


def _run(text):
    exporter = DictExporter()
    tracer = Tracer(exporters=[exporter])
    set_default_tracer(tracer)
    callback = TraceCastCallback(tracer=tracer)
    app = _build_app()

    @trace_cast(tracer=tracer, project_id="suporte", user_id="u1")
    def handle(message):
        return app.invoke({"text": message}, config={"callbacks": [callback]})

    handle(text)
    return exporter


def test_e2e_captures_full_flow():
    exporter = _run("hello world")
    reader = TraceReader([exporter])
    traces = reader.get_traces()
    assert len(traces) == 1
    t = traces[0]

    assert t.project_id == "suporte"
    assert t.latency_ms is not None and t.latency_ms >= 0

    types = [s.type for s in t.spans]
    assert SpanType.LLM in types
    assert SpanType.TOOL in types
    assert SpanType.AGENT in types

    llm = next(s for s in t.spans if s.type == SpanType.LLM)
    assert llm.tokens_in == 12
    assert llm.tokens_out == 4
    assert llm.cost_usd > 0
    assert t.total_tokens == 16

    node_spans = [s for s in t.spans if s.type == SpanType.AGENT]
    assert any(s.parent_span_id is not None for s in node_spans), "nós devem ter pai (grafo)"


def test_e2e_conditional_branch_b():
    exporter = _run("goodbye")
    t = TraceReader([exporter]).get_traces()[0]
    names = [s.name for s in t.spans if s.type == SpanType.AGENT]
    assert any("answer_b" in n for n in names)
    assert not any("answer_a" in n for n in names)


def test_e2e_dashboard_graph_and_filters():
    exporter = _run("hello world")
    tracer = Tracer(exporters=[exporter])
    app = FastAPI()
    tracer.mount(app, prefix="/tc")
    client = TestClient(app)

    listing = client.get("/tc/api/traces", params={"project_id": "suporte"})
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    trace_id = body["traces"][0]["trace_id"]

    other = client.get("/tc/api/traces", params={"project_id": "inexistente"})
    assert other.json()["total"] == 0

    graph = client.get(f"/tc/api/traces/{trace_id}/graph")
    assert graph.status_code == 200
    g = graph.json()
    assert len(g["nodes"]) >= 3
    assert all("id" in n and "type" in n for n in g["nodes"])
