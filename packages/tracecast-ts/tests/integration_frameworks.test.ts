import { Tracer } from "../src/core/tracer";
import { calculateCost } from "../src/core/costCalculator";
import { JsonFileExporter } from "../src/exporters/jsonFile";
import { Trace, Span, SpanType } from "../src/types";
import { randomUUID } from "crypto";
import { existsSync, readFileSync, rmSync } from "fs";
import { mkdtemp } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";

class CapturingExporter {
  readonly records: Trace[] = [];
  export(trace: Trace): void { this.records.push(trace); }
}

function makeSpan(
  model: string,
  type: SpanType,
  tokensIn: number,
  tokensOut: number,
): Span {
  return {
    spanId: randomUUID(),
    type,
    name: `${type}:${model}`,
    model: type === SpanType.LLM ? model : undefined,
    startedAt: new Date(),
    finishedAt: new Date(),
    tokensIn,
    tokensOut,
    costUsd: calculateCost(model, tokensIn, tokensOut),
  };
}

let langGraphAvailable = false;
let StateGraph: any;
let END_NODE: any;

try {
  ({ StateGraph, END: END_NODE } = require("@langchain/langgraph"));
  langGraphAvailable = true;
} catch {
  langGraphAvailable = false;
}

const describeIfLangGraph = langGraphAvailable ? describe : describe.skip;

describe("SDK direto — OpenAI style", () => {
  test("span manual simula openai.chat.completions.create", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    const mockResp = {
      model: "gpt-4o",
      usage: { prompt_tokens: 150, completion_tokens: 75 },
      choices: [{ message: { content: "Olá!" } }],
    };

    await tracer.trace("openai-sdk-test", async (trace) => {
      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${mockResp.model}`,
        model: mockResp.model,
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn:  mockResp.usage.prompt_tokens,
        tokensOut: mockResp.usage.completion_tokens,
        costUsd:   calculateCost(mockResp.model, mockResp.usage.prompt_tokens, mockResp.usage.completion_tokens),
      };
      trace.spans.push(span);
    }, { userId: "usr-1" });

    const exported = exp.records[0];
    expect(exported.totalTokensIn).toBe(150);
    expect(exported.totalTokensOut).toBe(75);
    expect(exported.totalTokens).toBe(225);
    expect(exported.costUsd).toBeGreaterThan(0);
    expect(exported.model).toBe("gpt-4o");
    expect(exported.userId).toBe("usr-1");
  });

  test("multiplas chamadas LLM acumulam tokens corretamente", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("multi-call-openai", async (trace) => {
      trace.spans.push(makeSpan("gpt-4o",      SpanType.LLM, 100, 50));
      trace.spans.push(makeSpan("gpt-4o-mini", SpanType.LLM, 200, 100));
    });

    const exported = exp.records[0];
    expect(exported.totalTokens).toBe(450);
    expect(exported.model).toBe("gpt-4o-mini");
  });

  test("tool call estilo OpenAI (function calling)", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("openai-tool-call", async (trace) => {
      trace.spans.push(makeSpan("gpt-4o", SpanType.LLM, 200, 50));
      trace.spans.push({
        spanId: randomUUID(),
        type: SpanType.TOOL,
        name: "get_weather",
        startedAt: new Date(),
        finishedAt: new Date(),
      });
    });

    const exported = exp.records[0];
    expect(exported.toolsUsed["get_weather"]).toBe(1);
    expect(exported.model).toBe("gpt-4o");
  });

  test("trace com erro ainda exporta (try/finally)", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await expect(
      tracer.trace("openai-error", async (trace) => {
        trace.spans.push(makeSpan("gpt-4o", SpanType.LLM, 100, 0));
        throw new Error("rate limit exceeded");
      })
    ).rejects.toThrow("rate limit exceeded");

    expect(exp.records).toHaveLength(1);
    expect(exp.records[0].finishedAt).toBeDefined();
    expect(exp.records[0].metadata._error).toBe("rate limit exceeded");
  });

  test("exporta para JSONL com campos corretos", async () => {
    const tmpDir = await mkdtemp(join(tmpdir(), "tc-test-"));
    const path = join(tmpDir, "openai.jsonl");

    const tracer = new Tracer({ exporters: [new JsonFileExporter(path)] });

    await tracer.trace("openai-jsonl", async (trace) => {
      trace.spans.push(makeSpan("gpt-4.1", SpanType.LLM, 300, 150));
    }, { userId: "alice", projectId: "proj-x" });

    const data = JSON.parse(readFileSync(path, "utf-8").trim());
    expect(data.userId).toBe("alice");
    expect(data.projectId).toBe("proj-x");
    expect(data.model).toBe("gpt-4.1");
    expect(data.totalTokens).toBe(450);
    expect(data.costUsd).toBeGreaterThan(0);

    rmSync(tmpDir, { recursive: true });
  });
});

describe("SDK direto — Anthropic style", () => {
  test("span manual simula anthropic.messages.create", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    const mockMsg = {
      model: "claude-sonnet-4-6",
      usage: { input_tokens: 120, output_tokens: 80 },
      content: [{ type: "text", text: "Olá!" }],
    };

    await tracer.trace("anthropic-sdk-test", async (trace) => {
      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${mockMsg.model}`,
        model: mockMsg.model,
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn:  mockMsg.usage.input_tokens,
        tokensOut: mockMsg.usage.output_tokens,
        costUsd:   calculateCost(mockMsg.model, mockMsg.usage.input_tokens, mockMsg.usage.output_tokens),
      };
      trace.spans.push(span);
    }, { userId: "usr-2" });

    const exported = exp.records[0];
    expect(exported.totalTokensIn).toBe(120);
    expect(exported.totalTokensOut).toBe(80);
    expect(exported.totalTokens).toBe(200);
    expect(exported.costUsd).toBeGreaterThan(0);
    expect(exported.model).toBe("claude-sonnet-4-6");
  });

  test("custo claude-opus-4-6 calculado corretamente", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("opus-cost", async (trace) => {
      trace.spans.push(makeSpan("claude-opus-4-6", SpanType.LLM, 1000, 500));
    });

    const expectedCost = (1000 / 1000) * 0.005 + (500 / 1000) * 0.025;
    expect(exp.records[0].costUsd).toBeCloseTo(expectedCost);
  });

  test("haiku é significativamente mais barato que opus", async () => {
    const costOpus  = calculateCost("claude-opus-4-6",   1000, 1000);
    const costHaiku = calculateCost("claude-haiku-4-5",  1000, 1000);
    expect(costOpus).toBeGreaterThan(costHaiku * 3);
  });
});

describe("SDK direto — Groq / Llama-4", () => {
  test("llama-4-scout com ID Groq completo calcula custo correto", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    const groqModelId = "meta-llama/llama-4-scout-17b-16e-instruct";

    await tracer.trace("groq-llama4-scout", async (trace) => {
      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${groqModelId}`,
        model: groqModelId,
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn: 500,
        tokensOut: 250,
        costUsd: calculateCost(groqModelId, 500, 250),
      };
      trace.spans.push(span);
    });

    const exported = exp.records[0];
    expect(exported.costUsd).toBeGreaterThan(0);
    const expected = (500 / 1000) * 0.00011 + (250 / 1000) * 0.00034;
    expect(exported.costUsd).toBeCloseTo(expected);
  });

  test("llama-4-scout alias curto tambem funciona", async () => {
    const costFull  = calculateCost("meta-llama/llama-4-scout-17b-16e-instruct", 1000, 1000);
    const costAlias = calculateCost("llama-4-scout", 1000, 1000);
    expect(costFull).toBeCloseTo(costAlias);
  });

  test("llama-4-maverick span com alias", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("groq-maverick", async (trace) => {
      trace.spans.push(makeSpan("llama-4-maverick", SpanType.LLM, 1000, 500));
    });

    expect(exp.records[0].costUsd).toBeGreaterThan(0);
    expect(exp.records[0].model).toBe("llama-4-maverick");
  });

  test("ollama modelo local tem custo zero", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("ollama-test", async (trace) => {
      trace.spans.push({
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: "llm:ollama/llama3",
        model: "ollama/llama3",
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn: 9999,
        tokensOut: 9999,
        costUsd: calculateCost("ollama/llama3", 9999, 9999),
      });
    });

    expect(exp.records[0].costUsd).toBe(0);
  });
});

describe("SDK direto — Google Gemini", () => {
  test("gemini-2.5-flash span com custo correto", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("gemini-flash-test", async (trace) => {
      trace.spans.push(makeSpan("gemini-2.5-flash", SpanType.LLM, 1000, 500));
    });

    const expected = (1000 / 1000) * 0.00030 + (500 / 1000) * 0.00250;
    expect(exp.records[0].costUsd).toBeCloseTo(expected);
  });

  test("gemini-2.5-pro mais caro que flash", () => {
    const flash = calculateCost("gemini-2.5-flash", 1000, 1000);
    const pro   = calculateCost("gemini-2.5-pro",   1000, 1000);
    expect(pro).toBeGreaterThan(flash);
  });
});

describeIfLangGraph("LangGraph.js — integração real (StateGraph)", () => {
  let FakeChatModel: any;
  let AIMessage: any;

  beforeAll(() => {
    try {
      ({ FakeChatModel } = require("@langchain/core/utils/testing"));
      ({ AIMessage } = require("@langchain/core/messages"));
    } catch {
      FakeChatModel = null;
    }
  });

  test("StateGraph com 2 nós gera spans AGENT via chain callbacks", async () => {
    const { TraceCastCallback } = require("../src/integrations/langchain");
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });
    const cb = new TraceCastCallback(tracer);

    function nodeA(state: { step: number }) { return { step: state.step + 1 }; }
    function nodeB(state: { step: number }) { return { step: state.step + 1 }; }

    const graph = new StateGraph({ channels: { step: { default: () => 0, reducer: (a: number, b: number) => b } } })
      .addNode("nodeA", nodeA)
      .addNode("nodeB", nodeB)
      .addEdge("__start__", "nodeA")
      .addEdge("nodeA", "nodeB")
      .addEdge("nodeB", "__end__")
      .compile();

    await tracer.trace("langgraph-test", async () => {
      await graph.invoke({ step: 0 }, { callbacks: [cb] });
    });

    const exported = exp.records[0];
    expect(exported.finishedAt).toBeDefined();
    const agentSpans = exported.spans.filter((s) => s.type === SpanType.AGENT);
    expect(agentSpans.length).toBeGreaterThanOrEqual(1);
  });
});

describe("Multi-framework — trace com múltiplos provedores", () => {
  test("trace orquestra OpenAI + Anthropic + Groq em sequência", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("multi-provider-agent", async (trace) => {
      trace.spans.push(makeSpan("gpt-4o-mini", SpanType.LLM, 50, 20));

      trace.spans.push({
        spanId: randomUUID(),
        type: SpanType.TOOL,
        name: "vector_search",
        startedAt: new Date(),
        finishedAt: new Date(),
      });

      trace.spans.push(makeSpan("claude-sonnet-4-6", SpanType.LLM, 500, 300));

      trace.spans.push(makeSpan("llama-4-scout", SpanType.LLM, 100, 50));
    }, { userId: "multi-usr", projectId: "multi-agent-proj" });

    const exported = exp.records[0];

    expect(exported.totalTokens).toBe(50 + 20 + 500 + 300 + 100 + 50);

    expect(exported.model).toBe("claude-sonnet-4-6");

    expect(exported.toolsUsed["vector_search"]).toBe(1);

    expect(exported.costUsd).toBeGreaterThan(0);

    expect(exported.userId).toBe("multi-usr");
    expect(exported.projectId).toBe("multi-agent-proj");
  });
});
