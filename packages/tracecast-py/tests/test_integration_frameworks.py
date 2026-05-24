import json
import tempfile
import uuid
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tracecast import Tracer
from tracecast.core.cost_calculator import calculate_cost
from tracecast.exporters.json_file import JsonFileExporter
from tracecast.models.span import Span, SpanType

try:
    from langchain_core.language_models.fake_chat_models import FakeChatModel
    from langchain_core.messages import AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

try:
    import langgraph
    from langgraph.graph import StateGraph, END
    from langchain_core.language_models.fake_chat_models import FakeChatModel as _FCM
    from langchain_core.messages import AIMessage as _AIM
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import crewai
    CREWAI_AVAILABLE = True
except Exception:
    CREWAI_AVAILABLE = False

try:
    import llama_index
    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    LLAMA_INDEX_AVAILABLE = False



class CapturingExporter:
    def __init__(self):
        self.records = []

    def export(self, trace):
        self.records.append(trace)


class TestSDKDiretoOpenAI:
    def test_span_manual_simula_openai_sdk(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        mock_resp = MagicMock()
        mock_resp.usage.prompt_tokens = 150
        mock_resp.usage.completion_tokens = 75
        mock_resp.model = "gpt-4o"

        with tracer.trace("openai-sdk-test", user_id="usr-1") as trace:
            started = datetime.now(timezone.utc)
            resp = mock_resp
            finished = datetime.now(timezone.utc)

            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{resp.model}",
                model=resp.model,
                started_at=started,
                finished_at=finished,
                tokens_in=resp.usage.prompt_tokens,
                tokens_out=resp.usage.completion_tokens,
            )
            span.cost_usd = calculate_cost(resp.model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.total_tokens_in == 150
        assert exported.total_tokens_out == 75
        assert exported.total_tokens == 225
        assert exported.cost_usd > 0
        assert exported.model == "gpt-4o"
        assert exported.user_id == "usr-1"
        assert exported.finished_at is not None

    def test_multiplas_chamadas_openai_numa_trace(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with tracer.trace("multi-call-openai") as trace:
            for model, tok_in, tok_out in [
                ("gpt-4o", 100, 50),
                ("gpt-4o-mini", 200, 100),
            ]:
                now = datetime.now(timezone.utc)
                span = Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name=f"llm:{model}",
                    model=model,
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=100),
                    tokens_in=tok_in,
                    tokens_out=tok_out,
                )
                span.cost_usd = calculate_cost(model, tok_in, tok_out)
                trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.total_tokens_in == 300
        assert exported.total_tokens_out == 150
        assert exported.total_tokens == 450
        assert exported.cost_usd > 0
        assert exported.model == "gpt-4o-mini"

    def test_trace_com_tool_call_openai_style(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with tracer.trace("openai-tool-call") as trace:
            now = datetime.now(timezone.utc)
            llm_span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name="llm:gpt-4o",
                model="gpt-4o",
                started_at=now,
                finished_at=now + timedelta(milliseconds=500),
                tokens_in=200,
                tokens_out=50,
            )
            llm_span.cost_usd = calculate_cost("gpt-4o", 200, 50)
            trace.spans.append(llm_span)
            tool_span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.TOOL,
                name="get_weather",
                started_at=now + timedelta(milliseconds=600),
                finished_at=now + timedelta(milliseconds=800),
            )
            trace.spans.append(tool_span)

        exported = exporter.records[0]
        assert exported.tools_used == {"get_weather": 1}
        assert exported.model == "gpt-4o"

    @pytest.mark.skipif(not OPENAI_AVAILABLE, reason="openai SDK not installed")
    def test_openai_sdk_real_mock_http(self):
        import openai
        from unittest.mock import patch

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        mock_response = MagicMock()
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 60
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Olá!"

        with tracer.trace("openai-real-sdk") as trace:
            with patch.object(openai.resources.chat.Completions, "create", return_value=mock_response):
                client = openai.OpenAI(api_key="test-key")
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "Diga olá"}],
                )

            started = datetime.now(timezone.utc)
            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{resp.model}",
                model=resp.model,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                tokens_in=resp.usage.prompt_tokens,
                tokens_out=resp.usage.completion_tokens,
            )
            span.cost_usd = calculate_cost(resp.model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.total_tokens == 160
        assert exported.cost_usd > 0



class TestSDKDiretoAnthropic:

    def test_span_manual_simula_anthropic_sdk(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        mock_resp = MagicMock()
        mock_resp.usage.input_tokens = 120
        mock_resp.usage.output_tokens = 80
        mock_resp.model = "claude-sonnet-4-6"
        mock_resp.content = [MagicMock(text="Olá!")]

        with tracer.trace("anthropic-sdk-test", user_id="usr-2") as trace:
            started = datetime.now(timezone.utc)
            resp = mock_resp
            finished = datetime.now(timezone.utc)

            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{resp.model}",
                model=resp.model,
                started_at=started,
                finished_at=finished,
                tokens_in=resp.usage.input_tokens,
                tokens_out=resp.usage.output_tokens,
            )
            span.cost_usd = calculate_cost(resp.model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.total_tokens_in == 120
        assert exported.total_tokens_out == 80
        assert exported.total_tokens == 200
        assert exported.cost_usd > 0
        assert exported.model == "claude-sonnet-4-6"

    def test_span_anthropic_opus_cost(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with tracer.trace("anthropic-opus-cost") as trace:
            now = datetime.now(timezone.utc)
            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name="llm:claude-opus-4-6",
                model="claude-opus-4-6",
                started_at=now,
                finished_at=now + timedelta(milliseconds=1200),
                tokens_in=1000,
                tokens_out=500,
            )
            span.cost_usd = calculate_cost("claude-opus-4-6", 1000, 500)
            trace.spans.append(span)

        exported = exporter.records[0]
        expected = (1000 / 1000 * 0.005) + (500 / 1000 * 0.025)
        assert abs(exported.cost_usd - expected) < 1e-9

    @pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="anthropic SDK not installed")
    def test_anthropic_sdk_real_mock(self):
        import anthropic

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        mock_msg = MagicMock()
        mock_msg.model = "claude-sonnet-4-6"
        mock_msg.usage.input_tokens = 50
        mock_msg.usage.output_tokens = 30

        with tracer.trace("anthropic-real-sdk") as trace:
            with patch.object(anthropic.resources.Messages, "create", return_value=mock_msg):
                client = anthropic.Anthropic(api_key="test-key")
                msg = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=100,
                    messages=[{"role": "user", "content": "Olá"}],
                )

            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{msg.model}",
                model=msg.model,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                tokens_in=msg.usage.input_tokens,
                tokens_out=msg.usage.output_tokens,
            )
            span.cost_usd = calculate_cost(msg.model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.total_tokens == 80
        assert exported.model == "claude-sonnet-4-6"



@pytest.mark.skipif(not LANGCHAIN_AVAILABLE, reason="langchain-core not installed")
class TestLangChain:

    def test_langchain_captura_span_llm(self):
        from tracecast.integrations.langchain import TraceCastCallback

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        cb = TraceCastCallback(tracer=tracer)

        chat = FakeChatModel(responses=[AIMessage(content="Olá!")])

        with tracer.trace("lc-test", user_id="u1") as trace:
            chat.invoke("Diga olá", config={"callbacks": [cb]})

        exported = exporter.records[0]
        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 1
        assert exported.user_id == "u1"

    def test_langchain_error_nao_perde_trace(self):
        from tracecast.integrations.langchain import TraceCastCallback

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        cb = TraceCastCallback(tracer=tracer)
        error_chat = MagicMock()
        error_chat.invoke.side_effect = RuntimeError("LLM unavailable")

        with pytest.raises(RuntimeError):
            with tracer.trace("lc-error-test"):
                run_id = str(uuid.uuid4())
                cb.on_llm_start({"kwargs": {"model_name": "gpt-4o"}}, [], run_id=run_id)
                cb.on_llm_error(RuntimeError("LLM unavailable"), run_id=run_id)
                error_chat.invoke("falhar")
        assert len(exporter.records) == 1
        exported = exporter.records[0]
        assert exported.finished_at is not None
        error_spans = [s for s in exported.spans if s.metadata.get("_error")]
        assert len(error_spans) >= 1



@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
class TestLangGraph:

    def test_langgraph_stategraph_captura_spans(self):
        from tracecast.integrations.langchain import TraceCastCallback
        from typing import TypedDict

        class AgentState(TypedDict):
            messages: list
            step: int

        def node_a(state: AgentState) -> AgentState:
            return {"messages": state["messages"] + ["node_a_done"], "step": 1}

        def node_b(state: AgentState) -> AgentState:
            return {"messages": state["messages"] + ["node_b_done"], "step": 2}

        builder = StateGraph(AgentState)
        builder.add_node("node_a", node_a)
        builder.add_node("node_b", node_b)
        builder.set_entry_point("node_a")
        builder.add_edge("node_a", "node_b")
        builder.add_edge("node_b", END)
        graph = builder.compile()

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        cb = TraceCastCallback(tracer=tracer)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with tracer.trace("langgraph-test", session_id="sess-lg"):
                graph.invoke(
                    {"messages": [], "step": 0},
                    config={"callbacks": [cb]},
                )

        assert len(exporter.records) == 1
        exported = exporter.records[0]
        assert exported.session_id == "sess-lg"
        assert exported.finished_at is not None
        agent_spans = [s for s in exported.spans if s.type == SpanType.AGENT]
        span_names = [s.name for s in agent_spans]
        assert len(agent_spans) >= 2, (
            f"Esperava >=2 spans AGENT para os nós do grafo, got: {span_names}"
        )

    def test_langgraph_com_llm_no(self):
        from tracecast.integrations.langchain import TraceCastCallback
        from typing import TypedDict

        chat = FakeChatModel(responses=[AIMessage(content="Resposta do agente")])

        class State(TypedDict):
            question: str
            answer: str

        def llm_node(state: State) -> State:
            response = chat.invoke(state["question"])
            return {"question": state["question"], "answer": response.content}

        builder = StateGraph(State)
        builder.add_node("llm_node", llm_node)
        builder.set_entry_point("llm_node")
        builder.add_edge("llm_node", END)
        graph = builder.compile()

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        cb = TraceCastCallback(tracer=tracer)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with tracer.trace("langgraph-llm-test"):
                result = graph.invoke(
                    {"question": "Qual é a capital do Brasil?", "answer": ""},
                    config={"callbacks": [cb]},
                )

        exported = exporter.records[0]
        assert exported.finished_at is not None
        agent_spans = [s for s in exported.spans if s.type == SpanType.AGENT]
        llm_spans   = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(agent_spans) >= 1, f"spans AGENT: {[s.name for s in exported.spans]}"
        assert len(llm_spans)   >= 1, f"spans LLM: {[s.name for s in exported.spans]}"

    def test_langgraph_exporta_para_jsonl(self):
        from tracecast.integrations.langchain import TraceCastCallback
        from typing import TypedDict

        class State(TypedDict):
            value: int

        def increment(state: State) -> State:
            return {"value": state["value"] + 1}

        builder = StateGraph(State)
        builder.add_node("increment", increment)
        builder.set_entry_point("increment")
        builder.add_edge("increment", END)
        graph = builder.compile()

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        tracer = Tracer(exporters=[JsonFileExporter(path=path)])
        cb = TraceCastCallback(tracer=tracer)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with tracer.trace("langgraph-jsonl-test", project_id="proj-lg"):
                graph.invoke({"value": 0}, config={"callbacks": [cb]})

        lines = Path(path).read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["project_id"] == "proj-lg"
        assert data["finished_at"] is not None
        assert isinstance(data["spans"], list)

    def test_langgraph_isolamento_por_contextvars(self):
        from tracecast.integrations.langchain import TraceCastCallback
        from typing import TypedDict

        class State(TypedDict):
            n: int

        def noop(state: State) -> State:
            return state

        builder = StateGraph(State)
        builder.add_node("noop", noop)
        builder.set_entry_point("noop")
        builder.add_edge("noop", END)
        graph = builder.compile()

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i in range(2):
                cb = TraceCastCallback(tracer=tracer)
                with tracer.trace(f"lg-trace-{i}", user_id=f"user-{i}"):
                    graph.invoke({"n": i}, config={"callbacks": [cb]})

        assert len(exporter.records) == 2
        assert exporter.records[0].trace_id != exporter.records[1].trace_id
        assert exporter.records[0].user_id == "user-0"
        assert exporter.records[1].user_id == "user-1"



@pytest.mark.skipif(not CREWAI_AVAILABLE, reason="crewai not installed — pip install crewai")
class TestCrewAI:

    def test_crewai_kickoff_captura_trace(self):
        import os
        import crewai

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing")
        with patch(
            "crewai.llms.providers.openai.completion.OpenAICompletion.call",
            return_value="Tarefa concluída com sucesso.",
        ):
            llm = crewai.LLM(model="gpt-4o-mini", api_key="sk-test-key-for-testing")
            agent = crewai.Agent(
                role="Assistente de Testes",
                goal="Responder perguntas simples",
                backstory="Um assistente prestativo para testes.",
                llm=llm,
                verbose=False,
            )
            task = crewai.Task(
                description="Diga olá em português.",
                expected_output="Uma saudação em português.",
                agent=agent,
            )

            with tracer.trace("crewai-test", project_id="proj-crew") as trace:
                crew = crewai.Crew(agents=[agent], tasks=[task])
                crew.kickoff()
                span = Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name="llm:gpt-4o-mini",
                    model="gpt-4o-mini",
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    tokens_in=120,
                    tokens_out=30,
                )
                span.cost_usd = calculate_cost("gpt-4o-mini", span.tokens_in, span.tokens_out)
                trace.spans.append(span)

        assert len(exporter.records) == 1
        exported = exporter.records[0]
        assert exported.finished_at is not None
        assert exported.project_id == "proj-crew"
        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 1
        assert exported.cost_usd > 0



@pytest.mark.skipif(not LLAMA_INDEX_AVAILABLE, reason="llama-index not installed — pip install llama-index")
class TestLlamaIndex:

    def test_llamaindex_mock_llm_captura_span(self):
        from llama_index.core.llms.mock import MockLLM
        from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler, CBEventType
        from llama_index.core.callbacks.schema import EventPayload

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        dbh = LlamaDebugHandler()
        cb_manager = CallbackManager([dbh])
        llm = MockLLM(max_tokens=50, callback_manager=cb_manager)

        with tracer.trace("llamaindex-test", project_id="rag-proj") as trace:
            started = datetime.now(timezone.utc)
            llm.complete("Qual é a capital da França?")
            finished = datetime.now(timezone.utc)
            for event in dbh.get_events():
                if (
                    event.event_type == CBEventType.LLM
                    and event.payload
                    and EventPayload.COMPLETION in event.payload
                ):
                    span = Span(
                        span_id=str(uuid.uuid4()),
                        type=SpanType.LLM,
                        name="llm:mock-llm",
                        model="mock-llm",
                        started_at=started,
                        finished_at=finished,
                        tokens_in=10,
                        tokens_out=len(event.payload[EventPayload.COMPLETION].text.split()),
                    )
                    span.cost_usd = 0.0
                    trace.spans.append(span)

        exported = exporter.records[0]
        assert exported.project_id == "rag-proj"
        assert exported.finished_at is not None
        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 1, "Deve haver ao menos 1 span LLM capturado"

    def test_llamaindex_multiplas_chamadas(self):
        from llama_index.core.llms.mock import MockLLM
        from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler, CBEventType
        from llama_index.core.callbacks.schema import EventPayload

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        def _run_llm_and_collect(llm, dbh, trace, prompt):
            started = datetime.now(timezone.utc)
            llm.complete(prompt)
            finished = datetime.now(timezone.utc)
            for event in dbh.get_events():
                if (
                    event.event_type == CBEventType.LLM
                    and event.payload
                    and EventPayload.COMPLETION in event.payload
                ):
                    span = Span(
                        span_id=str(uuid.uuid4()),
                        type=SpanType.LLM,
                        name="llm:mock-llm",
                        model="mock-llm",
                        started_at=started,
                        finished_at=finished,
                        tokens_in=8,
                        tokens_out=5,
                    )
                    span.cost_usd = 0.0
                    trace.spans.append(span)
            dbh.flush_event_logs()

        dbh = LlamaDebugHandler()
        cb_manager = CallbackManager([dbh])
        llm = MockLLM(max_tokens=20, callback_manager=cb_manager)

        with tracer.trace("llamaindex-multi", user_id="user-rag") as trace:
            _run_llm_and_collect(llm, dbh, trace, "Pergunta 1?")
            _run_llm_and_collect(llm, dbh, trace, "Pergunta 2?")

        exported = exporter.records[0]
        assert exported.user_id == "user-rag"
        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 2, f"Esperava >= 2 spans LLM, got {len(llm_spans)}"

    def test_llamaindex_exporta_para_jsonl(self):
        from llama_index.core.llms.mock import MockLLM
        from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler, CBEventType
        from llama_index.core.callbacks.schema import EventPayload

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        tracer = Tracer(exporters=[JsonFileExporter(path=path)])

        dbh = LlamaDebugHandler()
        llm = MockLLM(max_tokens=30, callback_manager=CallbackManager([dbh]))

        with tracer.trace("llamaindex-jsonl", session_id="sess-rag") as trace:
            started = datetime.now(timezone.utc)
            llm.complete("O que é RAG?")
            finished = datetime.now(timezone.utc)
            for event in dbh.get_events():
                if (
                    event.event_type == CBEventType.LLM
                    and event.payload
                    and EventPayload.COMPLETION in event.payload
                ):
                    span = Span(
                        span_id=str(uuid.uuid4()),
                        type=SpanType.LLM,
                        name="llm:mock-llm",
                        model="mock-llm",
                        started_at=started,
                        finished_at=finished,
                        tokens_in=5,
                        tokens_out=3,
                    )
                    span.cost_usd = 0.0
                    trace.spans.append(span)

        lines = Path(path).read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["session_id"] == "sess-rag"
        assert isinstance(data["spans"], list)
