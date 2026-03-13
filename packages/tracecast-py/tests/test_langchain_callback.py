import uuid
from unittest.mock import MagicMock
from tracecast.core.tracer import Tracer
from tracecast.integrations.langchain import TraceCastCallback
from tracecast.models.span import SpanType


def _run_id():
    return uuid.uuid4()

def test_on_llm_start_cria_span():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test"):
        cb.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}},
            prompts=["ola"],
            run_id=run_id,
        )
        assert str(run_id) in cb._span_stack


def test_on_llm_start_usa_model_quando_model_name_ausente():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test"):
        cb.on_llm_start(
            serialized={"kwargs": {"model": "gpt-4.1"}},
            prompts=[],
            run_id=run_id,
        )
        span = cb._span_stack[str(run_id)]
        assert span.model == "gpt-4.1"


def test_on_llm_end_adiciona_span_ao_trace():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}},
            prompts=["ola"],
            run_id=run_id,
        )
        mock_result = MagicMock()
        mock_result.llm_output = {
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 50}
        }
        cb.on_llm_end(mock_result, run_id=run_id)
        assert len(trace.spans) == 1
        span = trace.spans[0]
        assert span.type == SpanType.LLM
        assert span.tokens_in == 100
        assert span.tokens_out == 50
        assert span.cost_usd > 0


def test_on_llm_error_fecha_span_com_erro():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}},
            prompts=[],
            run_id=run_id,
        )
        cb.on_llm_error(Exception("llm failed"), run_id=run_id)
    assert str(run_id) not in cb._span_stack
    assert len(trace.spans) == 1
    assert trace.spans[0].metadata.get("_error") == "llm failed"
    assert trace.spans[0].finished_at is not None


def test_on_llm_error_sem_span_previo_nao_lanca():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    with tracer.trace("test"):
        cb.on_llm_error(Exception("orphan"), run_id=_run_id())

def test_on_tool_start_e_end_registra_span():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_tool_start(
            serialized={"name": "search_docs"},
            input_str="query",
            run_id=run_id,
        )
        cb.on_tool_end("resultado", run_id=run_id)
        assert len(trace.spans) == 1
        assert trace.spans[0].type == SpanType.TOOL
        assert trace.spans[0].name == "search_docs"


def test_on_tool_error_fecha_span_com_erro():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_tool_start({"name": "broken_tool"}, "input", run_id=run_id)
        cb.on_tool_error(Exception("tool broke"), run_id=run_id)

    assert str(run_id) not in cb._span_stack
    assert len(trace.spans) == 1
    assert trace.spans[0].metadata.get("_error") == "tool broke"

def test_on_chain_start_e_end_registra_span_de_agent():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_chain_start(
            serialized={"id": ["my", "module", "MyChain"]},
            inputs={},
            run_id=run_id,
        )
        cb.on_chain_end({}, run_id=run_id)

    assert len(trace.spans) == 1
    assert trace.spans[0].type == SpanType.AGENT
    assert trace.spans[0].name == "chain:MyChain"


def test_on_chain_error_fecha_span():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()
    with tracer.trace("test") as trace:
        cb.on_chain_start({"name": "MyNode"}, {}, run_id=run_id)
        cb.on_chain_error(Exception("node failed"), run_id=run_id)

    assert str(run_id) not in cb._span_stack
    assert len(trace.spans) == 1
    assert trace.spans[0].metadata.get("_error") == "node failed"

def test_span_stack_vazio_apos_fluxo_completo():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    ids = [_run_id() for _ in range(3)]

    with tracer.trace("test"):
        for rid in ids:
            cb.on_llm_start({"kwargs": {"model_name": "gpt-4o"}}, [], run_id=rid)
        for rid in ids:
            mock_result = MagicMock()
            mock_result.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}
            cb.on_llm_end(mock_result, run_id=rid)

    assert len(cb._span_stack) == 0


def test_span_stack_vazio_apos_erros():
    tracer = Tracer()
    cb = TraceCastCallback(tracer=tracer)
    run_id = _run_id()

    with tracer.trace("test"):
        cb.on_llm_start({"kwargs": {"model_name": "gpt-4o"}}, [], run_id=run_id)
        cb.on_llm_error(Exception("fail"), run_id=run_id)

    assert len(cb._span_stack) == 0
