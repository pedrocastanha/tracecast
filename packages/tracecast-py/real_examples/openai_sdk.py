import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

import openai
from tracecast import Span, SpanType, Tracer, calculate_cost
from tracecast.exporters import DictExporter, JsonFileExporter

logging.basicConfig(level=logging.INFO, format="%(message)s")

tracer = Tracer(
    exporters=[
        JsonFileExporter("./traces/openai_traces.jsonl"),
        DictExporter(
            on_trace=lambda d: print(
                f"[METRICS] trace={d['trace_id'][:8]} cost=${d['cost_usd']:.4f}"
            ),
        ),
    ],
    logging=True,
    log_prefix="openai_agent",
)

client = openai.OpenAI()


def search_web(query: str) -> str:
    return f"Resultado simulado para: {query}"


def run_agent(user_question: str, user_id: str, session_id: str) -> str:
    with tracer.trace(
        "openai_agent_run",
        user_id=user_id,
        session_id=session_id,
        project_id="demo_project",
        metadata={"question": user_question, "framework": "openai-sdk"},
    ) as trace:

        t0 = datetime.now(timezone.utc)
        resp1 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente de pesquisa preciso."},
                {"role": "user", "content": user_question},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Busca informações na internet",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }],
            tool_choice="auto",
        )
        t1 = datetime.now(timezone.utc)

        span_llm1 = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llm:gpt-4o-mini:call1",
            model="gpt-4o-mini",
            started_at=t0,
            finished_at=t1,
            tokens_in=resp1.usage.prompt_tokens,
            tokens_out=resp1.usage.completion_tokens,
        )
        span_llm1.cost_usd = calculate_cost("gpt-4o-mini", span_llm1.tokens_in, span_llm1.tokens_out)
        trace.spans.append(span_llm1)

        tool_result = None
        if resp1.choices[0].message.tool_calls:
            tc = resp1.choices[0].message.tool_calls[0]
            tool_name = tc.function.name
            args = json.loads(tc.function.arguments)

            t_tool_start = datetime.now(timezone.utc)
            tool_result = search_web(args["query"])
            t_tool_end = datetime.now(timezone.utc)

            trace.spans.append(Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.TOOL,
                name=tool_name,
                started_at=t_tool_start,
                finished_at=t_tool_end,
                metadata={"input": args, "output_preview": tool_result[:100]},
            ))

        messages = [
            {"role": "system", "content": "Você é um assistente de pesquisa preciso."},
            {"role": "user", "content": user_question},
        ]
        if tool_result:
            messages += [
                {"role": "assistant", "content": None, "tool_calls": resp1.choices[0].message.tool_calls},
                {
                    "role": "tool",
                    "tool_call_id": resp1.choices[0].message.tool_calls[0].id,
                    "content": tool_result,
                },
            ]

        t2 = datetime.now(timezone.utc)
        resp2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        t3 = datetime.now(timezone.utc)

        span_llm2 = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llm:gpt-4o-mini:call2",
            model="gpt-4o-mini",
            started_at=t2,
            finished_at=t3,
            tokens_in=resp2.usage.prompt_tokens,
            tokens_out=resp2.usage.completion_tokens,
        )
        span_llm2.cost_usd = calculate_cost("gpt-4o-mini", span_llm2.tokens_in, span_llm2.tokens_out)
        trace.spans.append(span_llm2)

        return resp2.choices[0].message.content


if __name__ == "__main__":
    answer = run_agent(
        user_question="Quem é Pedro Castanheira?",
        user_id="user_pedro",
        session_id="session_demo_001",
    )
    print(f"\nResposta: {answer}")
