import { Tracer } from "../src/core/tracer";
import { TraceCastCallback } from "../src/integrations/langchain";
import { SpanType } from "../src/types";

function makeRunId() {
  return "run-" + Math.random().toString(36).slice(2);
}

test("handleLLMStart cria span no stack", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("test", async () => {
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, ["hello"], runId);
    expect((cb as any).spans.has(runId)).toBe(true);
    const span = (cb as any).spans.get(runId);
    expect(span.model).toBe("gpt-4o");
    expect(span.type).toBe(SpanType.LLM);
  });
});

test("handleLLMStart usa model quando model_name ausente", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("test", async () => {
    await cb.handleLLMStart({ kwargs: { model: "gpt-4.1" } }, [], runId);
    const span = (cb as any).spans.get(runId);
    expect(span.model).toBe("gpt-4.1");
  });
});

test("handleLLMEnd adiciona span ao trace com tokens e custo", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, ["hello"], runId);
    await cb.handleLLMEnd(
      { llmOutput: { tokenUsage: { promptTokens: 100, completionTokens: 50 } } },
      runId,
    );
  });

  expect(capturedTrace.spans).toHaveLength(1);
  const span = capturedTrace.spans[0];
  expect(span.type).toBe(SpanType.LLM);
  expect(span.tokensIn).toBe(100);
  expect(span.tokensOut).toBe(50);
  expect(span.costUsd).toBeGreaterThan(0);
  expect(span.finishedAt).toBeDefined();
});

test("handleLLMEnd sem handleLLMStart nao lanca erro", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  await expect(cb.handleLLMEnd({ llmOutput: {} }, "orphan-run-id")).resolves.toBeUndefined();
});

test("handleLLMError remove span e registra erro em metadata", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, [], runId);
    await cb.handleLLMError(new Error("llm failed"), runId);
  });

  expect((cb as any).spans.has(runId)).toBe(false);
  expect(capturedTrace.spans).toHaveLength(1);
  expect(capturedTrace.spans[0].metadata._error).toBe("llm failed");
  expect(capturedTrace.spans[0].finishedAt).toBeDefined();
});

test("handleLLMError sem span previo nao lanca erro", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  await expect(
    cb.handleLLMError(new Error("orphan"), "no-such-run")
  ).resolves.toBeUndefined();
});

test("handleToolStart e handleToolEnd registra span de tool", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleToolStart({ name: "search_docs" }, "query", runId);
    await cb.handleToolEnd("resultado", runId);
  });

  expect(capturedTrace.spans).toHaveLength(1);
  expect(capturedTrace.spans[0].type).toBe(SpanType.TOOL);
  expect(capturedTrace.spans[0].name).toBe("search_docs");
  expect(capturedTrace.spans[0].finishedAt).toBeDefined();
});

test("handleToolError remove span e registra erro", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleToolStart({ name: "broken_tool" }, "input", runId);
    await cb.handleToolError(new Error("tool broke"), runId);
  });

  expect((cb as any).spans.has(runId)).toBe(false);
  expect(capturedTrace.spans).toHaveLength(1);
  expect(capturedTrace.spans[0].metadata._error).toBe("tool broke");
});

test("handleChainStart e handleChainEnd registra span de agent", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleChainStart({ id: ["my", "MyChain"] }, {}, runId);
    await cb.handleChainEnd({}, runId);
  });

  expect(capturedTrace.spans).toHaveLength(1);
  expect(capturedTrace.spans[0].type).toBe(SpanType.AGENT);
  expect(capturedTrace.spans[0].name).toBe("chain:MyChain");
});

test("handleChainError remove span e registra erro", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  let capturedTrace: any;
  await tracer.trace("test", async (t) => {
    capturedTrace = t;
    await cb.handleChainStart({ name: "MyNode" }, {}, runId);
    await cb.handleChainError(new Error("node failed"), runId);
  });

  expect((cb as any).spans.has(runId)).toBe(false);
  expect(capturedTrace.spans).toHaveLength(1);
  expect(capturedTrace.spans[0].metadata._error).toBe("node failed");
});

test("spans map fica vazio apos fluxo completo (sem orfaos)", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);

  await tracer.trace("test", async () => {
    const ids = [makeRunId(), makeRunId(), makeRunId()];
    for (const id of ids) {
      await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, [], id);
    }
    for (const id of ids) {
      await cb.handleLLMEnd({ llmOutput: { tokenUsage: { promptTokens: 10, completionTokens: 5 } } }, id);
    }
  });

  expect((cb as any).spans.size).toBe(0);
});

test("spans map fica vazio apos erros (sem orfaos)", async () => {
  const tracer = new Tracer();
  const cb = new TraceCastCallback(tracer);
  const runId = makeRunId();

  await tracer.trace("test", async () => {
    await cb.handleLLMStart({ kwargs: { model_name: "gpt-4o" } }, [], runId);
    await cb.handleLLMError(new Error("fail"), runId);
  });

  expect((cb as any).spans.size).toBe(0);
});
