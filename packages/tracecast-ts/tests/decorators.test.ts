import { traceCast, setDefaultTracer, Tracer, DictExporter } from "../src";

describe("traceCast", () => {
  test("uses the default tracer configured after wrapping", async () => {
    const exporter = new DictExporter();

    const route = traceCast(async () => "ok", { name: "route-after-default" });
    setDefaultTracer(new Tracer({ exporters: [exporter] }));

    await expect(route()).resolves.toBe("ok");
    expect(exporter.traces).toHaveLength(1);
    expect(exporter.traces[0].name).toBe("route-after-default");
  });
});
