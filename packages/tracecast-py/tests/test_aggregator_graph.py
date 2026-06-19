from datetime import datetime, timezone, timedelta

from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType
from tracecast.dashboard.aggregator import build_graph


_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _span(span_id, name, type_, pid, ti=0, to=0, model=None, input=None, order=0):
    started = _T0 + timedelta(seconds=order)
    return Span(
        span_id=span_id,
        type=type_,
        name=name,
        started_at=started,
        finished_at=started + timedelta(milliseconds=100),
        parent_span_id=pid,
        model=model,
        tokens_in=ti,
        tokens_out=to,
        cost_usd=round((ti + to) * 0.000001, 6),
        input=input,
    )


def _bia_like_trace():
    spans = [
        _span("root", "chain:LangGraph", SpanType.AGENT, None, order=0),
        _span("router_node", "chain:router_node", SpanType.AGENT, "root", order=1),
        _span("router_llm", "llm:gpt-4.1", SpanType.LLM, "router_node", ti=1867, to=18, model="gpt-4.1", order=2),
        _span("route", "chain:route_by_intent", SpanType.AGENT, "router_node", order=3),
        _span("service_node", "chain:service_node", SpanType.AGENT, "root", order=4),
        _span("inner_lg", "chain:LangGraph", SpanType.AGENT, "service_node", order=5),
        _span("agent", "chain:agent", SpanType.AGENT, "inner_lg", order=6),
        _span("runseq", "chain:RunnableSequence", SpanType.AGENT, "agent", order=7),
        _span("svc_llm1", "llm:gpt-4.1", SpanType.LLM, "runseq", ti=17155, to=76, model="gpt-4.1", order=8),
        _span("svc_llm2", "llm:gpt-4.1", SpanType.LLM, "runseq", ti=17755, to=157, model="gpt-4.1", order=9),
        _span("tools", "chain:tools", SpanType.AGENT, "inner_lg", order=10),
        _span("tool1", "search_knowledge_base", SpanType.TOOL, "tools",
              input="{'query': 'tecnologia tecnólogo graduação EAD', 'tipo': 'info_curso'}", order=11),
        _span("rerank1", "llm:gpt-4.1-nano", SpanType.LLM, "tool1", ti=1800, to=27, model="gpt-4.1-nano", order=12),
        _span("tool2", "search_knowledge_base", SpanType.TOOL, "tools",
              input="{'query': 'engenharia software computação bacharelado EAD', 'tipo': 'info_curso'}", order=13),
        _span("rerank2", "llm:gpt-4.1-nano", SpanType.LLM, "tool2", ti=840, to=17, model="gpt-4.1-nano", order=14),
        _span("final", "chain:final_response", SpanType.AGENT, "root", order=15),
        _span("orphan", "llm:gpt-4.1-nano", SpanType.LLM, None, ti=0, to=0, model="gpt-4.1-nano", order=16),
    ]
    return Trace(trace_id="t1", name="bia_graph", started_at=_T0, spans=spans)


def _nodes_by_id(graph):
    return {n["id"]: n for n in graph["nodes"]}


def test_orphan_llm_dropped():
    g = build_graph(_bia_like_trace())
    assert "orphan" not in _nodes_by_id(g)


def test_attribution_targets():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert n["router_node"]["own_total_tokens"] == 1885
    assert n["service_node"]["own_total_tokens"] == 35143
    assert n["route"]["own_total_tokens"] == 0
    assert n["final"]["own_total_tokens"] == 0


def test_reranker_attributes_to_tool():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert n["tool1"]["own_total_tokens"] == 1827
    assert n["tool2"]["own_total_tokens"] == 857


def test_no_double_count():
    g = build_graph(_bia_like_trace())
    total_own = sum(node["own_total_tokens"] for node in g["nodes"])
    llm_total = 1885 + 17231 + 17912 + 1827 + 857
    assert total_own == llm_total


def test_llm_span_itself_not_a_node():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert "router_llm" not in n
    assert "svc_llm1" not in n
    assert "rerank1" not in n


def test_llm_calls_per_node():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert len(n["service_node"]["llm_calls"]) == 2
    assert len(n["tool1"]["llm_calls"]) == 1
    assert n["route"]["llm_calls"] == []
    call = n["tool1"]["llm_calls"][0]
    assert call["model"] == "gpt-4.1-nano"
    assert call["tokens_in"] == 1800
    assert call["tokens_out"] == 27


def test_primary_model_largest_call():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert n["service_node"]["primary_model"] == "gpt-4.1"
    assert n["tool1"]["primary_model"] == "gpt-4.1-nano"
    assert n["route"]["primary_model"] is None


def test_trace_totals():
    g = build_graph(_bia_like_trace())
    assert g["total_tokens"] == 1885 + 17231 + 17912 + 1827 + 857
    assert g["total_tokens_in"] == 1867 + 17155 + 17755 + 1800 + 840
    assert g["total_tokens_out"] == 18 + 76 + 157 + 27 + 17


def test_tool_params_pyrepr():
    n = _nodes_by_id(build_graph(_bia_like_trace()))
    assert n["tool1"]["tool_params"] == {
        "query": "tecnologia tecnólogo graduação EAD",
        "tipo": "info_curso",
    }


def test_tool_params_json():
    spans = [
        _span("root", "chain:LangGraph", SpanType.AGENT, None, order=0),
        _span("tj", "search_knowledge_base", SpanType.TOOL, "root",
              input='{"query": "x", "tipo": "y"}', order=1),
    ]
    n = _nodes_by_id(build_graph(Trace(trace_id="t", name="n", started_at=_T0, spans=spans)))
    assert n["tj"]["tool_params"] == {"query": "x", "tipo": "y"}


def test_tool_params_malformed_is_none():
    spans = [
        _span("root", "chain:LangGraph", SpanType.AGENT, None, order=0),
        _span("tm", "search_knowledge_base", SpanType.TOOL, "root", input="not a dict", order=1),
    ]
    n = _nodes_by_id(build_graph(Trace(trace_id="t", name="n", started_at=_T0, spans=spans)))
    assert n["tm"]["tool_params"] is None


def _cspan(span_id, name, type_, ti, to, model, start_s, end_s, display=False, order=None, input=None, pid=None):
    s = Span(
        span_id=span_id,
        type=type_,
        name=name,
        started_at=_T0 + timedelta(seconds=start_s),
        finished_at=_T0 + timedelta(seconds=end_s),
        parent_span_id=pid,
        model=model,
        tokens_in=ti,
        tokens_out=to,
        cost_usd=round((ti + to) * 0.000001, 6),
        input=input,
    )
    if display:
        s.metadata["tc_display"] = True
        if order is not None:
            s.metadata["tc_order"] = order
    return s


def _curated_trace():
    spans = [
        _cspan("ltm", "ltm_summarizer", SpanType.AGENT, 0, 0, None, 0, 2, display=True),
        _cspan("ltm_llm", "llm:gpt-4.1-nano", SpanType.LLM, 600, 10, "gpt-4.1-nano", 0.5, 1.5),
        _cspan("router", "router", SpanType.AGENT, 0, 0, None, 2, 4, display=True),
        _cspan("router_llm", "llm:gpt-4.1", SpanType.LLM, 1800, 18, "gpt-4.1", 2.5, 3.5),
        _cspan("chain_noise", "chain:RunnableSequence", SpanType.AGENT, 0, 0, None, 2.4, 3.6),
        _cspan("service", "service", SpanType.AGENT, 0, 0, None, 4, 9, display=True),
        _cspan("svc_llm1", "llm:gpt-4.1", SpanType.LLM, 17000, 76, "gpt-4.1", 4.5, 5.5),
        _cspan("tool", "search_knowledge_base", SpanType.TOOL, 0, 0, None, 6, 8, display=True,
               input="{'query': 'saúde graduação EAD', 'tipo': 'info_curso'}"),
        _cspan("rerank_llm", "llm:gpt-4.1-nano", SpanType.LLM, 600, 11, "gpt-4.1-nano", 6.5, 7.5),
        _cspan("svc_llm2", "llm:gpt-4.1", SpanType.LLM, 17500, 97, "gpt-4.1", 8.2, 8.9),
        _cspan("final", "final_response", SpanType.AGENT, 0, 0, None, 9.1, 9.2, display=True),
    ]
    return Trace(trace_id="c1", name="bia_graph", started_at=_T0, spans=spans)


def test_curated_nodes_only():
    n = _nodes_by_id(build_graph(_curated_trace()))
    assert set(n) == {"ltm", "router", "service", "tool", "final"}


def test_curated_attribution_by_containment():
    n = _nodes_by_id(build_graph(_curated_trace()))
    assert n["ltm"]["own_total_tokens"] == 610
    assert n["router"]["own_total_tokens"] == 1818
    assert n["service"]["own_total_tokens"] == 34673
    assert n["tool"]["own_total_tokens"] == 611
    assert n["final"]["own_total_tokens"] == 0


def test_curated_reranker_folds_into_tool():
    n = _nodes_by_id(build_graph(_curated_trace()))
    assert n["tool"]["primary_model"] == "gpt-4.1-nano"
    assert len(n["tool"]["llm_calls"]) == 1
    assert n["service"]["primary_model"] == "gpt-4.1"
    assert len(n["service"]["llm_calls"]) == 2


def test_curated_sum_equals_total():
    g = build_graph(_curated_trace())
    total_own = sum(node["own_total_tokens"] for node in g["nodes"])
    assert total_own == g["total_tokens"]
    assert g["total_tokens"] == 610 + 1818 + 17076 + 611 + 17597


def test_curated_order_by_timestamp():
    g = build_graph(_curated_trace())
    assert [node["id"] for node in g["nodes"]] == ["ltm", "router", "service", "tool", "final"]


def test_curated_explicit_order_overrides():
    t = _curated_trace()
    by = {s.span_id: s for s in t.spans}
    for sid, o in [("final", 1), ("service", 2), ("tool", 2.5), ("router", 3), ("ltm", 4)]:
        by[sid].metadata["tc_order"] = o
    g = build_graph(t)
    ids = [node["id"] for node in g["nodes"]]
    assert ids == ["final", "service", "tool", "router", "ltm"]


def test_curated_tool_nesting_edge():
    g = build_graph(_curated_trace())
    pairs = {(e["from"], e["to"]) for e in g["edges"]}
    assert ("service", "tool") in pairs
