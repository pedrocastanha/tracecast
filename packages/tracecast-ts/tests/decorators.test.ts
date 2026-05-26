import { traceCast, setDefaultTracer, Tracer, DictExporter, wrapOpenAI } from "../src";

describe("traceCast", () => {
  test("uses the default tracer configured after wrapping", async () => {
    const exporter = new DictExporter();

    const route = traceCast(async () => "ok", { name: "route-after-default" });
    setDefaultTracer(new Tracer({ exporters: [exporter] }));

    await expect(route()).resolves.toBe("ok");
    expect(exporter.traces).toHaveLength(1);
    expect(exporter.traces[0].name).toBe("route-after-default");
  });

  test("is the primary flow for wrapped llm tokens", async () => {
    const exporter = new DictExporter();
    const client = wrapOpenAI({
      chat: {
        completions: {
          create: async (kwargs: any) => ({
            model: kwargs.model,
            usage: {
              prompt_tokens: 90,
              completion_tokens: 30,
              prompt_tokens_details: { cached_tokens: 20 },
            },
            choices: [{ message: { content: "ok" } }],
          }),
        },
      },
    });

    const route = traceCast(async () => {
      await client.chat.completions.create({
        model: "gpt-4o",
        messages: [{ role: "user", content: "hello" }],
      });
      return "ok";
    }, { name: "decorated-llm-route", projectId: "decorator-main" });

    setDefaultTracer(new Tracer({ exporters: [exporter] }));

    await expect(route()).resolves.toBe("ok");
    const trace = exporter.traces[0] as any;

    expect(trace.name).toBe("decorated-llm-route");
    expect(trace.projectId).toBe("decorator-main");
    expect(trace.totalTokensIn).toBe(90);
    expect(trace.totalTokensOut).toBe(30);
    expect(trace.totalTokensInCached).toBe(20);
    expect(trace.totalTokens).toBe(120);
    expect(trace.spans[0].model).toBe("gpt-4o");
  });
});
