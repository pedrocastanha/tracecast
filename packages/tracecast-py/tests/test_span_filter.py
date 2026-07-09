from datetime import datetime, timezone

from tracecast.core.span_filter import (
    should_keep_span,
    filter_spans,
    apply_span_filter_to_trace,
    resolve_span_filter,
)
from tracecast.core.tracer import Tracer
from tracecast.exporters.dict_exporter import DictExporter
from tracecast.models.span import Span, SpanType
from tracecast.models.trace import Trace


def _span(sid, name, stype=SpanType.AGENT, parent=None, **meta):
    return Span(
        span_id=sid,
        name=name,
        type=stype,
        started_at=datetime.now(timezone.utc),
        parent_span_id=parent,
        metadata=meta,
    )


def test_resolve_span_filter_env(monkeypatch):
    monkeypatch.delenv("TRACECAST_SPAN_FILTER", raising=False)
    assert resolve_span_filter(None) == "all"
    assert resolve_span_filter("flow") == "flow"
    assert resolve_span_filter("LLM_TOOL") == "llm_tool"
    monkeypatch.setenv("TRACECAST_SPAN_FILTER", "flow")
    assert resolve_span_filter(None) == "flow"


def test_flow_keeps_nodes_llm_tool_drops_runnable():
    noise = _span("1", "chain:RunnableSequence")
    node = _span("2", "service_node", langgraph_node="service_node", tc_display=True)
    llm = _span("3", "llm:gpt-4o", SpanType.LLM, parent="1")
    tool = _span("4", "search_graduacao", SpanType.TOOL, parent="2")
    prompt = _span("5", "chain:Prompt")
    route = _span("6", "chain:route_after_guard")
    inner_agent = _span("7", "agent", langgraph_node="agent", tc_display=True)
    inner_tools = _span("8", "tools", langgraph_node="tools", tc_display=True)

    assert should_keep_span(noise, "flow") is False
    assert should_keep_span(node, "flow") is True
    assert should_keep_span(llm, "flow") is True
    assert should_keep_span(tool, "flow") is True
    assert should_keep_span(prompt, "flow") is False
    assert should_keep_span(route, "flow") is False
    assert should_keep_span(inner_agent, "flow") is False
    assert should_keep_span(inner_tools, "flow") is False


def test_reparent_after_drop():
    root = _span("root", "service_node", langgraph_node="service_node", tc_display=True)
    mid = _span("mid", "chain:RunnableSequence", parent="root")
    llm = _span("llm", "llm:gpt", SpanType.LLM, parent="mid")
    kept = filter_spans([root, mid, llm], "flow")
    by_id = {s.span_id: s for s in kept}
    assert set(by_id) == {"root", "llm"}
    assert by_id["llm"].parent_span_id == "root"


def test_llm_tool_mode():
    node = _span("n", "router_node", langgraph_node="router_node", tc_display=True)
    llm = _span("l", "llm:x", SpanType.LLM)
    tool = _span("t", "search", SpanType.TOOL)
    kept = filter_spans([node, llm, tool], "llm_tool")
    assert {s.span_id for s in kept} == {"l", "t"}


def test_tracer_applies_flow_filter():
    exp = DictExporter()
    tracer = Tracer(exporters=[exp], span_filter="flow", background_export=False)
    with tracer.trace("g") as t:
        t.spans.append(_span("a", "chain:RunnableSequence"))
        t.spans.append(_span("b", "router_node", langgraph_node="router_node", tc_display=True))
        t.spans.append(_span(
            "c", "llm:gpt-4o-mini", SpanType.LLM, parent="a",
        ))
        t.spans[-1].tokens_in = 10
        t.spans[-1].tokens_out = 5
        t.spans[-1].input = "hello prompt"
        t.spans[-1].output = "hello out"
        t.spans.append(_span("d", "search_x", SpanType.TOOL, parent="b"))
        t.spans[-1].input = '{"q":1}'
        t.spans[-1].output = "docs"
    assert len(exp.traces) == 1
    names = [s["name"] for s in exp.traces[0]["spans"]]
    assert "chain:RunnableSequence" not in names
    assert "router_node" in names
    assert "llm:gpt-4o-mini" in names
    assert "search_x" in names
    llm = next(s for s in exp.traces[0]["spans"] if s["name"].startswith("llm:"))
    assert llm["input"]
    assert llm["output"]
    assert exp.traces[0]["total_tokens"] == 15


def test_apply_stats():
    t = Trace(
        trace_id="x",
        name="n",
        started_at=datetime.now(timezone.utc),
        spans=[
            _span("1", "chain:Prompt"),
            _span("2", "final_response", tc_display=True),
        ],
    )
    stats = apply_span_filter_to_trace(t, "flow")
    assert stats["before"] == 2
    assert stats["after"] == 1
    assert stats["dropped"] == 1
