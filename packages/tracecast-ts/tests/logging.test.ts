import { TraceCastLogger } from "../src/core/logger";
import { Tracer } from "../src/core/tracer";
import { TraceCastCallback } from "../src/integrations/langchain";

test("logger usa prefix configurado", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger("meu_agente", (m) => logs.push(m));
  logger.traceStart("qualquer_nome");
  expect(logs[0]).toContain("[meu_agente]");
  expect(logs[0]).toContain("Trace started");
});

test("logger usa trace name quando sem prefix", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger(undefined, (m) => logs.push(m));
  logger.traceStart("meu_trace");
  expect(logs[0]).toContain("[meu_trace]");
});

test("logger trace end contém tokens, custo, latência e tools", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger("agent", (m) => logs.push(m));
  logger.traceEnd("agent", {
    totalTokens: 500,
    costUsd: 0.0025,
    latencyMs: 1200,
    toolsUsed: { search: 2 },
  });
  const line = logs[0];
  expect(line).toContain("500 tokens");
  expect(line).toContain("$0.0025");
  expect(line).toContain("1.20s");
  expect(line).toContain("search×2");
});

test("logger llm start e end numa única linha cada", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger("a", (m) => logs.push(m));
  logger.llmStart("a", "gpt-4o");
  logger.llmEnd("a", { model: "gpt-4o", tokensIn: 100, tokensOut: 50, costUsd: 0.001, latencyMs: 800 });

  expect(logs).toHaveLength(2);
  expect(logs[0]).not.toContain("\n");
  expect(logs[1]).not.toContain("\n");
  expect(logs[0]).toContain("LLM started → gpt-4o");
  expect(logs[1]).toContain("100 in / 50 out");
  expect(logs[1]).toContain("0.80s");
});

test("logger tool start colapsa input multiline", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger("a", (m) => logs.push(m));
  logger.toolStart("a", "my_tool", "linha1\nlinha2\nlinha3");
  expect(logs[0]).not.toContain("\n");
  expect(logs[0]).toContain("Tool call → my_tool");
});

test("logger tool end com latencia", () => {
  const logs: string[] = [];
  const logger = new TraceCastLogger("a", (m) => logs.push(m));
  logger.toolEnd("a", "search_web", 450);
  expect(logs[0]).toContain("0.45s");
});

test("logger error emite via warnFn", () => {
  const warns: string[] = [];
  const logger = new TraceCastLogger("a", undefined, (m) => warns.push(m));
  logger.llmError("a", "gpt-4o", "timeout");
  expect(warns[0]).toContain("⚠");
  expect(warns[0]).toContain("timeout");
});

test("Tracer sem logging nao cria logger", () => {
  const tracer = new Tracer({ logging: false });
  expect(tracer._logger).toBeNull();
});

test("Tracer com logging=true loga trace start e end", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logFn: (m) => logs.push(m) });
  await tracer.trace("meu_trace", async () => {});
  expect(logs.some((l) => l.includes("[meu_trace] Trace started"))).toBe(true);
  expect(logs.some((l) => l.includes("Trace finished"))).toBe(true);
});

test("Tracer com logPrefix usa prefix em vez do trace name", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logPrefix: "agente_x", logFn: (m) => logs.push(m) });
  await tracer.trace("qualquer", async () => {});
  expect(logs.every((l) => !l.includes("[qualquer]"))).toBe(true);
  expect(logs.some((l) => l.includes("[agente_x]"))).toBe(true);
});

test("Tracer trace end contém summary de tokens e custo", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logPrefix: "agent", logFn: (m) => logs.push(m) });
  await tracer.trace("qualquer", async () => {});
  const line = logs.find((l) => l.includes("Trace finished"))!;
  expect(line).toContain("tokens");
  expect(line).toContain("$");
});

function makeRunId() {
  return "run-" + Math.random().toString(36).slice(2);
}

test("callback loga llm start e end quando logging habilitado", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logPrefix: "cb_agent", logFn: (m) => logs.push(m) });
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("run", async () => {
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, [], runId);
    await cb.handleLLMEnd(
      { llmOutput: { tokenUsage: { promptTokens: 100, completionTokens: 50 } } },
      runId,
    );
  });

  expect(logs.some((l) => l.includes("LLM started → gpt-4o"))).toBe(true);
  expect(logs.some((l) => l.includes("LLM end → gpt-4o"))).toBe(true);
  expect(logs.some((l) => l.includes("100 in"))).toBe(true);
});

test("callback loga tool start e end", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logPrefix: "cb_agent", logFn: (m) => logs.push(m) });
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("run", async () => {
    await cb.handleToolStart({ name: "pesquisa" }, "minha query", runId);
    await cb.handleToolEnd("resultado", runId);
  });

  expect(logs.some((l) => l.includes("Tool call → pesquisa"))).toBe(true);
  expect(logs.some((l) => l.includes("minha query"))).toBe(true);
  expect(logs.some((l) => l.includes("Tool end → pesquisa"))).toBe(true);
});

test("callback sem logging nao emite logs de llm", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: false, logFn: (m) => logs.push(m) });
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("run", async () => {
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, [], runId);
    await cb.handleLLMEnd({ llmOutput: {} }, runId);
  });

  expect(logs.length).toBe(0);
});

test("callback loga chain apenas para no raiz (sem parentRunId)", async () => {
  const logs: string[] = [];
  const tracer = new Tracer({ logging: true, logPrefix: "cb_agent", logFn: (m) => logs.push(m) });
  const cb = new TraceCastCallback(tracer);
  const rootId = makeRunId();
  const childId = makeRunId();

  await tracer.trace("run", async () => {
    await cb.handleChainStart({ name: "RootChain" }, {}, rootId, undefined);
    await cb.handleChainStart({ name: "SubChain" }, {}, childId, rootId);
    await cb.handleChainEnd({}, childId);
    await cb.handleChainEnd({}, rootId);
  });

  const chainLogs = logs.filter((l) => l.includes("Chain →"));
  expect(chainLogs).toHaveLength(1);
  expect(chainLogs[0]).toContain("RootChain");
});
