import http from "http";
import { Tracer, DictExporter } from "../../src";

function request(server: http.Server, path: string): Promise<{ status: number; body: string }> {
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("server address unavailable");

  return new Promise((resolve, reject) => {
    const req = http.get({ host: "127.0.0.1", port: address.port, path }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        resolve({ status: res.statusCode ?? 0, body });
      });
    });
    req.on("error", reject);
  });
}

describe("Tracer.mount dashboard", () => {
  test("serves dashboard html and trace api from a real http route", async () => {
    const exporter = new DictExporter();
    const tracer = new Tracer({ exporters: [exporter] });

    await tracer.trace("mounted-dashboard-trace", async () => undefined, {
      projectId: "project-real",
    });

    const app = (_req: http.IncomingMessage, res: http.ServerResponse) => {
      res.writeHead(404);
      res.end("not found");
    };
    const server = tracer.mount(app, { prefix: "/observability" }) as http.Server;

    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

    try {
      const dashboard = await request(server, "/observability/");
      expect(dashboard.status).toBe(200);
      expect(dashboard.body).toContain("TraceCast Dashboard");

      const traces = await request(server, "/observability/api/traces");
      expect(traces.status).toBe(200);
      const data = JSON.parse(traces.body);
      expect(data.traces[0].name).toBe("mounted-dashboard-trace");
      expect(data.traces[0].project_id).toBe("project-real");
    } finally {
      await new Promise<void>((resolve, reject) => server.close((err) => err ? reject(err) : resolve()));
    }
  });
});
