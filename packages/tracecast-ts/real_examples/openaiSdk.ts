import path from "path";
import dotenv from "dotenv";
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });

import OpenAI from "openai";
import { randomUUID } from "crypto";
import { Tracer, JsonFileExporter, DictExporter, SpanType, calculateCost } from "../src";

const tracer = new Tracer({
  exporters: [
    new JsonFileExporter("./traces/ts_openai_traces.jsonl"),
    new DictExporter({
      onTrace: (d: any) =>
        console.log(`[METRICS] trace=${d.traceId.slice(0, 8)} cost=$${d.costUsd.toFixed(4)}`),
    }),
  ],
  logging: true,
  logPrefix: "ts_openai_agent",
});

const openai = new OpenAI();

function searchWeb(query: string): string {
  return `Resultado simulado para: ${query}`;
}

async function runAgent(userQuestion: string, userId: string, sessionId: string): Promise<string> {
  return tracer.trace(
    "openai_ts_agent_run",
    async (trace) => {
      const t0 = new Date();
      const resp1 = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: "Você é um assistente de pesquisa preciso." },
          { role: "user", content: userQuestion },
        ],
        tools: [{
          type: "function",
          function: {
            name: "search_web",
            description: "Busca informações na internet",
            parameters: {
              type: "object",
              properties: { query: { type: "string" } },
              required: ["query"],
            },
          },
        }],
        tool_choice: "auto",
      });
      const t1 = new Date();

      trace.spans.push({
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: "llm:gpt-4o-mini:call1",
        model: "gpt-4o-mini",
        startedAt: t0,
        finishedAt: t1,
        tokensIn: resp1.usage?.prompt_tokens ?? 0,
        tokensOut: resp1.usage?.completion_tokens ?? 0,
        costUsd: calculateCost("gpt-4o-mini", resp1.usage?.prompt_tokens ?? 0, resp1.usage?.completion_tokens ?? 0),
      });

      let toolResult: string | null = null;
      const toolCall = resp1.choices[0].message.tool_calls?.[0] as any;
      if (toolCall) {
        const args = JSON.parse(toolCall.function.arguments);
        const tToolStart = new Date();
        toolResult = searchWeb(args.query);
        const tToolEnd = new Date();

        trace.spans.push({
          spanId: randomUUID(),
          type: SpanType.TOOL,
          name: toolCall.function.name,
          startedAt: tToolStart,
          finishedAt: tToolEnd,
          metadata: { input: args, outputPreview: toolResult.slice(0, 100) },
        });
      }

      const messages: OpenAI.ChatCompletionMessageParam[] = [
        { role: "system", content: "Você é um assistente de pesquisa preciso." },
        { role: "user", content: userQuestion },
      ];
      if (toolResult && toolCall) {
        messages.push(
          { role: "assistant", content: null, tool_calls: [toolCall] },
          { role: "tool", tool_call_id: toolCall.id, content: toolResult },
        );
      }

      const t2 = new Date();
      const resp2 = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages,
      });
      const t3 = new Date();

      trace.spans.push({
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: "llm:gpt-4o-mini:call2",
        model: "gpt-4o-mini",
        startedAt: t2,
        finishedAt: t3,
        tokensIn: resp2.usage?.prompt_tokens ?? 0,
        tokensOut: resp2.usage?.completion_tokens ?? 0,
        costUsd: calculateCost("gpt-4o-mini", resp2.usage?.prompt_tokens ?? 0, resp2.usage?.completion_tokens ?? 0),
      });

      return resp2.choices[0].message.content ?? "";
    },
    { userId, sessionId, projectId: "demo_project", metadata: { question: userQuestion, framework: "openai-sdk" } },
  );
}

if (require.main === module) {
  runAgent("Quem é Pedro Castanheira?", "user_pedro", "session_demo_001")
    .then((answer) => console.log(`\nResposta: ${answer}`))
    .catch(console.error);
}
