import { Tracer } from "../src/core/tracer";
import { SpanType } from "../src/types";

test("trace executa callback e chama export", async () => {
  const exportedTraces: unknown[] = [];
  const mockExporter = { export: (t: unknown) => { exportedTraces.push(t); } };
  const tracer = new Tracer({ exporters: [mockExporter as any] });

  const result = await tracer.trace("test-agent", async (t) => {
    expect(tracer.currentTrace()).toBe(t);
    return "ok";
  });

  expect(result).toBe("ok");
  expect(exportedTraces).toHaveLength(1);
  const exported = exportedTraces[0] as any;
  expect(exported.finishedAt).toBeDefined();
  expect(exported.name).toBe("test-agent");
  expect(exported.latencyMs).toBeGreaterThanOrEqual(0);
});

test("currentTrace retorna null fora do trace", () => {
  const tracer = new Tracer();
  expect(tracer.currentTrace()).toBeNull();
});

test("trace retorna resultado do callback", async () => {
  const tracer = new Tracer();
  const result = await tracer.trace("calc", async () => 42);
  expect(result).toBe(42);
});

test("trace exporta mesmo quando callback lanca excecao", async () => {
  const exportedTraces: unknown[] = [];
  const mockExporter = { export: (t: unknown) => { exportedTraces.push(t); } };
  const tracer = new Tracer({ exporters: [mockExporter as any] });

  await expect(
    tracer.trace("failing-agent", async () => {
      throw new Error("boom");
    })
  ).rejects.toThrow("boom");

  expect(exportedTraces).toHaveLength(1);
  const exported = exportedTraces[0] as any;
  expect(exported.finishedAt).toBeDefined();
  expect(exported.latencyMs).toBeGreaterThanOrEqual(0);
});

test("trace rethrows erro original do usuario", async () => {
  const tracer = new Tracer();
  const originalError = new TypeError("tipo errado");

  await expect(
    tracer.trace("err-trace", async () => { throw originalError; })
  ).rejects.toThrow("tipo errado");
});

test("trace grava _error em metadata quando callback lanca", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await expect(
    tracer.trace("err-trace", async () => { throw new Error("falha"); })
  ).rejects.toThrow();

  expect(exportedTraces[0].metadata._error).toBe("falha");
});

test("currentTrace esta limpo apos excecao", async () => {
  const tracer = new Tracer();
  await expect(
    tracer.trace("err", async () => { throw new Error("x"); })
  ).rejects.toThrow();
  expect(tracer.currentTrace()).toBeNull();
});

test("exporter que lanca nao derruba o trace por padrao", async () => {
  const badExporter  = { export: (_: any) => { throw new Error("disk full"); } };
  const goodCapture: any[] = [];
  const goodExporter = { export: (t: any) => { goodCapture.push(t); } };

  const tracer = new Tracer({ exporters: [badExporter, goodExporter] });

  await expect(
    tracer.trace("safe", async () => "result")
  ).resolves.toBe("result");

  expect(goodCapture).toHaveLength(1);
});

test("failOnExportError=true propaga falha do exporter", async () => {
  const badExporter = { export: (_: any) => { throw new Error("disk full"); } };
  const tracer = new Tracer({ exporters: [badExporter], failOnExportError: true });

  await expect(
    tracer.trace("strict", async () => "result")
  ).rejects.toThrow("disk full");
});

test("trace agrega tokens e custo dos spans", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await tracer.trace("span-test", async (t) => {
    t.spans.push({
      spanId: "s1",
      type: SpanType.LLM,
      name: "llm:gpt-4o",
      model: "gpt-4o",
      startedAt: new Date(),
      tokensIn: 100,
      tokensOut: 50,
      costUsd: 0.00075,
    });
  });

  const tr = exportedTraces[0];
  expect(tr.totalTokensIn).toBe(100);
  expect(tr.totalTokensOut).toBe(50);
  expect(tr.totalTokens).toBe(150);
  expect(tr.costUsd).toBeCloseTo(0.00075);
});

test("trace conta tools usadas nos spans", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await tracer.trace("tools-test", async (t) => {
    t.spans.push({ spanId: "t1", type: SpanType.TOOL, name: "search", startedAt: new Date() });
    t.spans.push({ spanId: "t2", type: SpanType.TOOL, name: "search", startedAt: new Date() });
    t.spans.push({ spanId: "t3", type: SpanType.TOOL, name: "calc", startedAt: new Date() });
  });

  const tr = exportedTraces[0];
  expect(tr.toolsUsed["search"]).toBe(2);
  expect(tr.toolsUsed["calc"]).toBe(1);
});

test("addSpan adiciona span ao trace corrente", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await tracer.trace("add-span", async () => {
    tracer.addSpan({
      spanId: "manual-1",
      type: SpanType.LLM,
      name: "llm:gpt-4o",
      model: "gpt-4o",
      startedAt: new Date(),
    });
  });

  expect(exportedTraces[0].spans).toHaveLength(1);
  expect(exportedTraces[0].spans[0].spanId).toBe("manual-1");
});

test("addSpan fora do trace nao lanca erro", () => {
  const tracer = new Tracer();
  expect(() =>
    tracer.addSpan({ spanId: "x", type: SpanType.LLM, name: "y", startedAt: new Date() })
  ).not.toThrow();
});

test("trace agrega totalTokensInCached dos spans", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await tracer.trace("cached-test", async (t) => {
    t.spans.push({
      spanId: "s1", type: SpanType.LLM, name: "llm:gpt-4o", model: "gpt-4o",
      startedAt: new Date(), tokensIn: 1000, tokensOut: 200, tokensInCached: 300,
    });
    t.spans.push({
      spanId: "s2", type: SpanType.LLM, name: "llm:claude-sonnet-4-6", model: "claude-sonnet-4-6",
      startedAt: new Date(), tokensIn: 500, tokensOut: 100, tokensInCached: 100,
    });
  });

  const tr = exportedTraces[0];
  expect(tr.totalTokensInCached).toBe(400);
});

test("trace com spans sem tokensInCached resulta em totalTokensInCached zero", async () => {
  const exportedTraces: any[] = [];
  const tracer = new Tracer({ exporters: [{ export: (t) => { exportedTraces.push(t); } }] });

  await tracer.trace("no-cache-test", async (t) => {
    t.spans.push({
      spanId: "s1", type: SpanType.LLM, name: "llm:gpt-4o", model: "gpt-4o",
      startedAt: new Date(), tokensIn: 100, tokensOut: 50,
    });
  });

  expect(exportedTraces[0].totalTokensInCached).toBe(0);
});
