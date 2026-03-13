import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

import anthropic
from tracecast import Span, SpanType, Tracer, calculate_cost
from tracecast.exporters import DictExporter, JsonFileExporter

logging.basicConfig(level=logging.INFO, format="%(message)s")

captured_traces = []
tracer = Tracer(
    exporters=[
        JsonFileExporter("./traces/anthropic_traces.jsonl", exclude_fields={"spans"}),
        DictExporter(on_trace=lambda d: captured_traces.append(d)),
    ],
    logging=True,
    log_prefix="support_agent",
)
client = anthropic.Anthropic()


def get_ticket_info(ticket_id: str) -> dict:
    return {
        "ticket_id": ticket_id,
        "customer": "Pedro Castanheira",
        "issue": "Erro 502 Bad Gateway na API de pagamentos",
        "priority": "high",
    }


def handle_ticket(ticket_id: str, user_id: str) -> str:
    with tracer.trace(
        "support_ticket_handler",
        user_id=user_id,
        project_id="support_system",
        session_id=f"ticket_{ticket_id}",
        metadata={"ticket_id": ticket_id, "framework": "anthropic-sdk"},
    ) as trace:
        prompt = f"Analise o ticket {ticket_id} e determine a melhor solução. Use a tool get_ticket_info para buscar os detalhes."

        t0 = datetime.now(timezone.utc)
        msg1 = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "get_ticket_info",
                "description": "Busca os detalhes de um ticket de suporte",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticket_id": {"type": "string"}},
                    "required": ["ticket_id"],
                },
            }],
        )
        t1 = datetime.now(timezone.utc)

        span_llm1 = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llm:claude:analyze",
            model="claude-haiku-4-5",
            started_at=t0,
            finished_at=t1,
            tokens_in=msg1.usage.input_tokens,
            tokens_out=msg1.usage.output_tokens,
        )
        span_llm1.cost_usd = calculate_cost("claude-haiku-4-5", span_llm1.tokens_in, span_llm1.tokens_out)
        trace.spans.append(span_llm1)

        tool_result_content = None
        for block in msg1.content:
            if block.type == "tool_use":
                t_s = datetime.now(timezone.utc)
                info = get_ticket_info(block.input["ticket_id"])
                t_e = datetime.now(timezone.utc)
                trace.spans.append(Span(
                    span_id=str(uuid.uuid4()),
                    type=SpanType.TOOL,
                    name=block.name,
                    started_at=t_s,
                    finished_at=t_e,
                    metadata={"input": block.input, "result": info},
                ))
                tool_result_content = (block.id, info)

        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": msg1.content},
        ]
        if tool_result_content:
            b_id, res = tool_result_content
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": b_id, "content": str(res)}],
            })

        t2 = datetime.now(timezone.utc)
        msg2 = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=messages,
        )
        t3 = datetime.now(timezone.utc)

        span_llm2 = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name="llm:claude:respond",
            model="claude-haiku-4-5",
            started_at=t2,
            finished_at=t3,
            tokens_in=msg2.usage.input_tokens,
            tokens_out=msg2.usage.output_tokens,
        )
        span_llm2.cost_usd = calculate_cost("claude-haiku-4-5", span_llm2.tokens_in, span_llm2.tokens_out)
        trace.spans.append(span_llm2)

        return msg2.content[0].text


if __name__ == "__main__":
    result = handle_ticket(ticket_id="TKT-9812", user_id="agent_001")
    print(f"\nResposta: {result}")
