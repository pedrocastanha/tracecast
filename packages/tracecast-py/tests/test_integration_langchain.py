import json
import tempfile
import uuid
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tracecast import Tracer
from tracecast.core.cost_calculator import calculate_cost
from tracecast.exporters.json_file import JsonFileExporter
from tracecast.integrations.langchain import TraceCastCallback
from tracecast.models.span import Span, SpanType

try:
    from langchain_community.llms.fake import FakeListLLM
    FAKE_LIST_LLM_AVAILABLE = True
except ImportError:
    try:
        from langchain.llms.fake import FakeListLLM
        FAKE_LIST_LLM_AVAILABLE = True
    except ImportError:
        FAKE_LIST_LLM_AVAILABLE = False

try:
    from langchain_core.prompts import PromptTemplate
    PROMPT_TEMPLATE_AVAILABLE = True
except ImportError:
    PROMPT_TEMPLATE_AVAILABLE = False

LANGCHAIN_AVAILABLE = FAKE_LIST_LLM_AVAILABLE and PROMPT_TEMPLATE_AVAILABLE

try:
    from langchain_core.language_models.fake_chat_models import FakeChatModel
    from langchain_core.messages import AIMessage
    FAKE_CHAT_AVAILABLE = True
except ImportError:
    FAKE_CHAT_AVAILABLE = False


class CapturingExporter:
    def __init__(self):
        self.records = []

    def export(self, trace):
        self.records.append(trace)


@pytest.mark.skipif(not LANGCHAIN_AVAILABLE, reason="langchain / langchain-community not installed")
class TestLangChainFakeListLLMIntegration:
    def test_tracer_captura_span_llm_via_callback_real(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            exporter = CapturingExporter()
            tracer = Tracer(exporters=[exporter])
            callback = TraceCastCallback(tracer=tracer)

            llm = FakeListLLM(responses=["Olá! Estou bem."])
            prompt = PromptTemplate.from_template("Diga olá: {input}")
            chain = prompt | llm

            with tracer.trace("langchain-integration-test", user_id="test-user"):
                chain.invoke({"input": "mundo"}, config={"callbacks": [callback]})

        assert len(exporter.records) == 1
        exported = exporter.records[0]
        assert exported.user_id == "test-user"
        assert exported.name == "langchain-integration-test"
        assert exported.finished_at is not None
        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 1, (
            f"Esperava pelo menos 1 span LLM registrado pelo callback real do LangChain, "
            f"mas got: {exported.spans}"
        )
        span = llm_spans[0]
        assert span.started_at is not None
        assert span.finished_at is not None
        assert span.finished_at >= span.started_at

    def test_tracer_exporta_para_jsonl_via_langchain_real(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
                path = f.name

            tracer = Tracer(exporters=[JsonFileExporter(path=path)])
            callback = TraceCastCallback(tracer=tracer)

            llm = FakeListLLM(responses=["Resposta fake do LLM."])
            prompt = PromptTemplate.from_template("{input}")
            chain = prompt | llm

            with tracer.trace("export-integration-test", project_id="proj-1"):
                chain.invoke({"input": "teste"}, config={"callbacks": [callback]})

        lines = Path(path).read_text().strip().splitlines()
        assert len(lines) == 1, f"Esperava exatamente 1 linha no JSONL, got {len(lines)}"

        data = json.loads(lines[0])
        assert data["project_id"] == "proj-1"
        assert "spans" in data
        assert data["finished_at"] is not None
        assert isinstance(data["spans"], list)
        assert len(data["spans"]) >= 1

    def test_multiplos_traces_isolados_por_contextvars(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            exporter = CapturingExporter()
            tracer = Tracer(exporters=[exporter])
            callback = TraceCastCallback(tracer=tracer)

            llm = FakeListLLM(responses=["r1", "r2"])
            prompt = PromptTemplate.from_template("{input}")
            chain = prompt | llm

            with tracer.trace("trace-1", user_id="user-1"):
                chain.invoke({"input": "a"}, config={"callbacks": [callback]})

            with tracer.trace("trace-2", user_id="user-2"):
                chain.invoke({"input": "b"}, config={"callbacks": [callback]})

        assert len(exporter.records) == 2

        t1, t2 = exporter.records
        assert t1.user_id == "user-1"
        assert t2.user_id == "user-2"
        assert t1.trace_id != t2.trace_id
        assert len(t1.spans) >= 1
        assert len(t2.spans) >= 1
        ids_t1 = {s.span_id for s in t1.spans}
        ids_t2 = {s.span_id for s in t2.spans}
        assert ids_t1.isdisjoint(ids_t2), "Spans de traces distintos não devem se misturar"

    def test_trace_sem_exporter_nao_lanca_excecao(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            tracer = Tracer(exporters=[])
            callback = TraceCastCallback(tracer=tracer)

            llm = FakeListLLM(responses=["ok"])
            prompt = PromptTemplate.from_template("{input}")
            chain = prompt | llm

            with tracer.trace("no-exporter-test") as trace:
                chain.invoke({"input": "x"}, config={"callbacks": [callback]})
            assert len(trace.spans) >= 1


@pytest.mark.skipif(not FAKE_CHAT_AVAILABLE, reason="langchain-core FakeChatModel not available")
class TestFakeChatModelIntegration:
    def test_chat_model_registra_span_llm(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        callback = TraceCastCallback(tracer=tracer)

        chat = FakeChatModel(responses=[AIMessage(content="Olá!")])

        with tracer.trace("chat-test") as trace:
            chat.invoke("Diga olá", config={"callbacks": [callback]})

        assert len(exporter.records) == 1
        exported = exporter.records[0]

        llm_spans = [s for s in exported.spans if s.type == SpanType.LLM]
        assert len(llm_spans) >= 1, (
            f"Esperava span LLM via FakeChatModel, got spans: {exported.spans}"
        )

        span = llm_spans[0]
        assert span.started_at is not None
        assert span.finished_at is not None

    def test_chat_model_trace_tem_timestamps_corretos(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])
        callback = TraceCastCallback(tracer=tracer)

        chat = FakeChatModel(responses=[AIMessage(content="Resposta")])

        with tracer.trace("chat-latency-test"):
            chat.invoke("prompt", config={"callbacks": [callback]})

        exported = exporter.records[0]
        assert exported.finished_at is not None
        assert exported.latency_ms is not None
        assert exported.latency_ms >= 0


class TestOpenAIDirectIntegration:
    def test_span_manual_openai_style(self):
        mock_response = MagicMock()
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 75

        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with tracer.trace("openai-direct-test", user_id="usr_42") as trace:
            started = datetime.now(timezone.utc)
            response = mock_response
            finished = datetime.now(timezone.utc)

            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name="llm:gpt-4o",
                model="gpt-4o",
                started_at=started,
                finished_at=finished,
                tokens_in=response.usage.prompt_tokens,
                tokens_out=response.usage.completion_tokens,
            )
            span.cost_usd = calculate_cost("gpt-4o", span.tokens_in, span.tokens_out)
            trace.spans.append(span)

        assert len(exporter.records) == 1
        exported = exporter.records[0]

        assert exported.total_tokens_in == 150
        assert exported.total_tokens_out == 75
        assert exported.total_tokens == 225
        assert exported.cost_usd > 0
        assert exported.model == "gpt-4o"
        assert exported.user_id == "usr_42"

    def test_multiplos_spans_numa_trace(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        now = datetime.now(timezone.utc)

        with tracer.trace("multi-span-test") as trace:
            trace.spans.extend([
                Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name="llm:gpt-4o",
                    model="gpt-4o",
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=500),
                    tokens_in=200,
                    tokens_out=100,
                    cost_usd=calculate_cost("gpt-4o", 200, 100),
                ),
                Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.TOOL,
                    name="search_docs",
                    started_at=now + timedelta(milliseconds=100),
                    finished_at=now + timedelta(milliseconds=300),
                ),
                Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.TOOL,
                    name="search_docs",
                    started_at=now + timedelta(milliseconds=400),
                    finished_at=now + timedelta(milliseconds=450),
                ),
            ])

        exported = exporter.records[0]
        assert exported.total_tokens == 300
        assert exported.tools_used == {"search_docs": 2}
        assert exported.model == "gpt-4o"
        assert exported.cost_usd > 0

    def test_trace_vazio_finaliza_sem_erros(self):
        exporter = CapturingExporter()
        tracer = Tracer(exporters=[exporter])

        with tracer.trace("empty-trace-test", session_id="sess-99"):
            pass

        assert len(exporter.records) == 1
        exported = exporter.records[0]

        assert exported.total_tokens == 0
        assert exported.total_tokens_in == 0
        assert exported.total_tokens_out == 0
        assert exported.cost_usd == 0.0
        assert exported.tools_used == {}
        assert exported.model is None
        assert exported.session_id == "sess-99"
        assert exported.finished_at is not None

    def test_trace_exportado_para_jsonl_span_manual(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        tracer = Tracer(exporters=[JsonFileExporter(path=path)])
        now = datetime.now(timezone.utc)

        with tracer.trace("jsonl-manual-test", project_id="proj-manual") as trace:
            trace.spans.append(
                Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name="llm:gpt-4o-mini",
                    model="gpt-4o-mini",
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=250),
                    tokens_in=50,
                    tokens_out=30,
                    cost_usd=calculate_cost("gpt-4o-mini", 50, 30),
                )
            )

        lines = Path(path).read_text().strip().splitlines()
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["project_id"] == "proj-manual"
        assert data["total_tokens"] == 80
        assert data["model"] == "gpt-4o-mini"
        assert data["cost_usd"] > 0
        assert data["finished_at"] is not None
        assert len(data["spans"]) == 1
