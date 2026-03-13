import { Tracer } from "../src/core/tracer";
import { TraceCastCallback } from "../src/integrations/langchain";
import { JsonFileExporter } from "../src/exporters/jsonFile";
import { Trace, SpanType } from "../src/types";
import { readFileSync, unlinkSync, existsSync } from "fs";

class CapturingExporter {
  readonly records: Trace[] = [];
  export(trace: Trace): void {
    this.records.push(trace);
  }
}

let FakeChatModel: any;
let AIMessage: any;
let langchainAvailable = false;

try {
  ({ FakeChatModel } = require("@langchain/core/utils/testing"));
  ({ AIMessage } = require("@langchain/core/messages"));
  langchainAvailable = true;
} catch {
  langchainAvailable = false;
}

const describeIfLangchain = langchainAvailable ? describe : describe.skip;

describeIfLangchain("LangChain.js — integração real com FakeChatModel", () => {
  test("TraceCastCallback registra span LLM via eventos reais do LangChain", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });
    const cb = new TraceCastCallback(tracer);

    const chat = new FakeChatModel({
      responses: [new AIMessage("Olá do FakeChatModel!")],
    });

    await tracer.trace("langchainjs-real-test", async () => {
      await chat.invoke("Diga olá", { callbacks: [cb] });
    });

    expect(exp.records).toHaveLength(1);
    const exported = exp.records[0];
    expect(exported.name).toBe("langchainjs-real-test");
    expect(exported.finishedAt).toBeDefined();

    const llmSpans = exported.spans.filter((s) => s.type === SpanType.LLM);
    expect(llmSpans.length).toBeGreaterThanOrEqual(1);

    expect(llmSpans[0].model).toBe("unknown");

    expect(llmSpans[0].startedAt).toBeInstanceOf(Date);
    expect(llmSpans[0].finishedAt).toBeInstanceOf(Date);
  });

  test("pipeline completo: FakeChatModel → TraceCastCallback → JsonFileExporter", async () => {
    const path = "/tmp/tracecast-ts-integration.jsonl";
    if (existsSync(path)) unlinkSync(path);

    const tracer = new Tracer({ exporters: [new JsonFileExporter(path)] });
    const cb = new TraceCastCallback(tracer);

    const chat = new FakeChatModel({
      responses: [new AIMessage("resposta fake")],
    });

    await tracer.trace(
      "jsonl-export-test",
      async () => {
        await chat.invoke("teste", { callbacks: [cb] });
      },
      { userId: "usr-ts-123", projectId: "proj-ts" },
    );

    expect(existsSync(path)).toBe(true);
    const lines = readFileSync(path, "utf-8").trim().split("\n");
    expect(lines).toHaveLength(1);

    const data = JSON.parse(lines[0]);
    expect(data.userId).toBe("usr-ts-123");
    expect(data.projectId).toBe("proj-ts");
    expect(data.finishedAt).toBeDefined();
    expect(Array.isArray(data.spans)).toBe(true);
    expect(data.spans.length).toBeGreaterThanOrEqual(1);

    expect(typeof data.latencyMs).toBe("number");
    expect(data.latencyMs).toBeGreaterThanOrEqual(0);
  });

  test("dois traces consecutivos são isolados por AsyncLocalStorage", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    const chat = new FakeChatModel({
      responses: [new AIMessage("r1"), new AIMessage("r2")],
    });

    await tracer.trace(
      "trace-1",
      async () => {
        const cb1 = new TraceCastCallback(tracer);
        await chat.invoke("a", { callbacks: [cb1] });
      },
      { userId: "user-1" },
    );

    await tracer.trace(
      "trace-2",
      async () => {
        const cb2 = new TraceCastCallback(tracer);
        await chat.invoke("b", { callbacks: [cb2] });
      },
      { userId: "user-2" },
    );

    expect(exp.records).toHaveLength(2);

    expect(exp.records[0].userId).toBe("user-1");
    expect(exp.records[1].userId).toBe("user-2");
    expect(exp.records[0].traceId).not.toBe(exp.records[1].traceId);

    expect(exp.records[0].spans.length).toBeGreaterThanOrEqual(1);
    expect(exp.records[1].spans.length).toBeGreaterThanOrEqual(1);
    const ids0 = exp.records[0].spans.map((s) => s.spanId);
    const ids1 = exp.records[1].spans.map((s) => s.spanId);
    const intersection = ids0.filter((id) => ids1.includes(id));
    expect(intersection).toHaveLength(0);
  });

  test("TraceCastCallback reutilizável em chamadas sequenciais dentro do mesmo tracer", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });
    const cb = new TraceCastCallback(tracer);

    const chat = new FakeChatModel({
      responses: [new AIMessage("x"), new AIMessage("y")],
    });

    await tracer.trace("seq-trace-1", async () => {
      await chat.invoke("msg1", { callbacks: [cb] });
    });

    await tracer.trace("seq-trace-2", async () => {
      await chat.invoke("msg2", { callbacks: [cb] });
    });

    expect(exp.records).toHaveLength(2);
    expect(exp.records[0].spans.length).toBeGreaterThanOrEqual(1);
    expect(exp.records[1].spans.length).toBeGreaterThanOrEqual(1);
  });
});

describe("Integração direta — spans manuais (sem LangChain)", () => {
  test("trace manual com 1 LLM span captura tokens e custo", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace(
      "manual-llm-test",
      async (trace) => {
        trace.spans.push({
          spanId: "span-1",
          type: SpanType.LLM,
          name: "llm:gpt-4o",
          model: "gpt-4o",
          startedAt: new Date(),
          finishedAt: new Date(),
          tokensIn: 200,
          tokensOut: 100,
          costUsd: (200 / 1000) * 0.0025 + (100 / 1000) * 0.01,
          metadata: {},
        });
      },
      { userId: "usr-42" },
    );

    expect(exp.records).toHaveLength(1);
    const exported = exp.records[0];
    expect(exported.totalTokensIn).toBe(200);
    expect(exported.totalTokensOut).toBe(100);
    expect(exported.totalTokens).toBe(300);
    expect(exported.costUsd).toBeGreaterThan(0);
    expect(exported.model).toBe("gpt-4o");
    expect(exported.userId).toBe("usr-42");
    expect(exported.finishedAt).toBeDefined();
    expect(exported.latencyMs).toBeGreaterThanOrEqual(0);
  });

  test("trace com 1 LLM + 2 TOOL spans calcula toolsUsed e tokens corretamente", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("multi-span-test", async (trace) => {
      trace.spans.push(
        {
          spanId: "s1",
          type: SpanType.LLM,
          name: "llm:gpt-4o",
          model: "gpt-4o",
          startedAt: new Date(),
          finishedAt: new Date(),
          tokensIn: 300,
          tokensOut: 150,
          costUsd: 0.003,
        },
        {
          spanId: "s2",
          type: SpanType.TOOL,
          name: "search_docs",
          startedAt: new Date(),
          finishedAt: new Date(),
        },
        {
          spanId: "s3",
          type: SpanType.TOOL,
          name: "search_docs",
          startedAt: new Date(),
          finishedAt: new Date(),
        },
      );
    });

    const exported = exp.records[0];
    expect(exported.toolsUsed).toEqual({ search_docs: 2 });
    expect(exported.totalTokensIn).toBe(300);
    expect(exported.totalTokensOut).toBe(150);
    expect(exported.totalTokens).toBe(450);
    expect(exported.costUsd).toBeCloseTo(0.003);
    expect(exported.model).toBe("gpt-4o");
  });

  test("modelo dominante é o LLM com maior volume de tokens", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("dominant-model-test", async (trace) => {
      trace.spans.push(
        {
          spanId: "s1",
          type: SpanType.LLM,
          name: "llm:gpt-4o-mini",
          model: "gpt-4o-mini",
          startedAt: new Date(),
          finishedAt: new Date(),
          tokensIn: 50,
          tokensOut: 20,
          costUsd: 0.00001,
        },
        {
          spanId: "s2",
          type: SpanType.LLM,
          name: "llm:gpt-4o",
          model: "gpt-4o",
          startedAt: new Date(),
          finishedAt: new Date(),
          tokensIn: 500,
          tokensOut: 300,
          costUsd: 0.005,
        },
      );
    });

    expect(exp.records[0].model).toBe("gpt-4o");
    expect(exp.records[0].totalTokens).toBe(870);
  });

  test("trace exportado para JSONL tem todos os campos serializados", async () => {
    const path = "/tmp/tracecast-ts-manual.jsonl";
    if (existsSync(path)) unlinkSync(path);

    const tracer = new Tracer({ exporters: [new JsonFileExporter(path)] });

    await tracer.trace(
      "jsonl-manual",
      async (trace) => {
        trace.spans.push({
          spanId: "s1",
          type: SpanType.LLM,
          name: "llm:claude-sonnet-4",
          model: "claude-sonnet-4",
          startedAt: new Date(),
          finishedAt: new Date(),
          tokensIn: 50,
          tokensOut: 30,
          costUsd: 0.0006,
        });
      },
      { sessionId: "sess-xyz", projectId: "proj-ts" },
    );

    expect(existsSync(path)).toBe(true);
    const raw = readFileSync(path, "utf-8").trim();
    expect(raw.split("\n")).toHaveLength(1);

    const data = JSON.parse(raw);
    expect(data.sessionId).toBe("sess-xyz");
    expect(data.projectId).toBe("proj-ts");
    expect(data.spans).toHaveLength(1);
    expect(data.spans[0].model).toBe("claude-sonnet-4");
    expect(data.totalTokens).toBe(80);
    expect(data.totalTokensIn).toBe(50);
    expect(data.totalTokensOut).toBe(30);
    expect(data.finishedAt).toBeDefined();
    expect(data.latencyMs).toBeGreaterThanOrEqual(0);
    expect(data.model).toBe("claude-sonnet-4");
  });

  test("dois traces em sequência acumulam linhas no mesmo arquivo JSONL", async () => {
    const path = "/tmp/tracecast-ts-multi.jsonl";
    if (existsSync(path)) unlinkSync(path);

    const exporter = new JsonFileExporter(path);
    const tracer = new Tracer({ exporters: [exporter] });

    await tracer.trace("trace-a", async (trace) => {
      trace.spans.push({
        spanId: "a1",
        type: SpanType.LLM,
        name: "llm:gpt-4o",
        model: "gpt-4o",
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn: 10,
        tokensOut: 5,
        costUsd: 0.0001,
      });
    }, { userId: "alice" });

    await tracer.trace("trace-b", async (trace) => {
      trace.spans.push({
        spanId: "b1",
        type: SpanType.LLM,
        name: "llm:gpt-4o",
        model: "gpt-4o",
        startedAt: new Date(),
        finishedAt: new Date(),
        tokensIn: 20,
        tokensOut: 10,
        costUsd: 0.0002,
      });
    }, { userId: "bob" });

    const lines = readFileSync(path, "utf-8").trim().split("\n");
    expect(lines).toHaveLength(2);

    const [first, second] = lines.map((l) => JSON.parse(l));
    expect(first.name).toBe("trace-a");
    expect(first.userId).toBe("alice");
    expect(second.name).toBe("trace-b");
    expect(second.userId).toBe("bob");
    expect(first.traceId).not.toBe(second.traceId);
  });

  test("trace sem spans resulta em zeros em todos os agregados", async () => {
    const exp = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exp] });

    await tracer.trace("empty-trace", async () => {
    });

    const exported = exp.records[0];
    expect(exported.spans).toHaveLength(0);
    expect(exported.totalTokensIn).toBe(0);
    expect(exported.totalTokensOut).toBe(0);
    expect(exported.totalTokens).toBe(0);
    expect(exported.costUsd).toBe(0);
    expect(exported.toolsUsed).toEqual({});
    expect(exported.model).toBeUndefined();
  });

  test("exporter que não lança não propaga exceção para o tracer", async () => {
    const silentExporter = {
      export: (_t: Trace): void => { },
    };

    const tracer = new Tracer({ exporters: [silentExporter] });

    await expect(
      tracer.trace("resilience-test", async () => "ok"),
    ).resolves.toBe("ok");
  });

  test("tracer retorna o valor retornado pelo callback", async () => {
    const tracer = new Tracer();

    const result = await tracer.trace("return-value-test", async () => {
      return { answer: 42 };
    });

    expect(result).toEqual({ answer: 42 });
  });

  test("currentTrace() retorna o trace ativo dentro do contexto e null fora", async () => {
    const tracer = new Tracer();

    let traceInsideContext: Trace | null = null;

    await tracer.trace("context-test", async (t) => {
      traceInsideContext = tracer.currentTrace();
      expect(traceInsideContext).toBe(t);
    });

    expect(tracer.currentTrace()).toBeNull();
    expect(traceInsideContext).not.toBeNull();
    expect((traceInsideContext as unknown as Trace).name).toBe("context-test");
  });
});
