import { Tracer, Trace, wrapOpenAI } from "../src";

class CapturingExporter {
  readonly records: Trace[] = [];

  export(trace: Trace): void {
    this.records.push(trace);
  }
}

describe("wrapOpenAI", () => {
  test("saves tokens and cached tokens into the active trace", async () => {
    const exporter = new CapturingExporter();
    const tracer = new Tracer({ exporters: [exporter] });
    const client = wrapOpenAI({
      chat: {
        completions: {
          create: async (kwargs: any) => ({
            model: kwargs.model,
            usage: {
              prompt_tokens: 120,
              completion_tokens: 40,
              prompt_tokens_details: { cached_tokens: 30 },
            },
            choices: [{ message: { content: "ok" } }],
          }),
        },
      },
    });

    await tracer.trace("wrapped-openai", async () => {
      await client.chat.completions.create({
        model: "gpt-4o",
        messages: [{ role: "user", content: "hello" }],
      });
    });

    const trace = exporter.records[0];
    const span = trace.spans[0];

    expect(trace.totalTokensIn).toBe(120);
    expect(trace.totalTokensOut).toBe(40);
    expect(trace.totalTokensInCached).toBe(30);
    expect(trace.totalTokens).toBe(160);
    expect(trace.model).toBe("gpt-4o");
    expect(span.tokensIn).toBe(120);
    expect(span.tokensOut).toBe(40);
    expect(span.tokensInCached).toBe(30);
    expect(span.costUsd).toBeGreaterThan(0);
  });
});
