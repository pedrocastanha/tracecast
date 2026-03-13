import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.callbacks import CallbackManager, CBEventType, LlamaDebugHandler
from tracecast import Span, SpanType, Tracer, calculate_cost

logging.basicConfig(level=logging.INFO, format="%(message)s")

tracer = Tracer(logging=True, log_prefix="llamaindex_rag")
llama_debug = LlamaDebugHandler(print_trace_on_end=False)
callback_manager = CallbackManager([llama_debug])


def query_rag(question: str):
    docs = [Document(text="TraceCast is an LLM observability SDK by Pedro Castanheira. It supports OpenAI, Anthropic, LangChain, LangGraph, CrewAI, and LlamaIndex.")]
    index = VectorStoreIndex.from_documents(docs, callback_manager=callback_manager)
    engine = index.as_query_engine()

    with tracer.trace("llamaindex_rag_query", user_id="user_pedro") as trace:
        response = engine.query(question)

        for event in llama_debug.get_events():
            if event.event_type == CBEventType.LLM:
                p = event.payload or {}
                model = p.get("model", "unknown")
                span = Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.LLM,
                    name=f"llm:{model}",
                    model=model,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    tokens_in=p.get("formatted_prompt_tokens_count", 0),
                    tokens_out=p.get("completion_tokens_count", 0),
                )
                span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out)
                trace.spans.append(span)

            elif event.event_type == CBEventType.RETRIEVE:
                trace.spans.append(Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.TOOL,
                    name="vector_retrieval",
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                ))

        return str(response)


if __name__ == "__main__":
    answer = query_rag("What is TraceCast?")
    print(f"\nResposta: {answer}")
