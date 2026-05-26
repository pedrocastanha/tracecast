const http = require("http");
const { DictExporter, Tracer, setDefaultTracer, traceCast } = require("tracecast");

const exporter = new DictExporter();
const runChat = traceCast(async () => ({ reply: "ok" }), {
  name: "node-smoke-chat",
  projectId: "real-node",
});
const tracer = new Tracer({ exporters: [exporter] });

setDefaultTracer(tracer);

const app = async (req, res) => {
  if ((req.url || "").split("?")[0] === "/chat") {
    const payload = await runChat();
    const body = JSON.stringify(payload);
    res.writeHead(200, {
      "content-type": "application/json; charset=utf-8",
      "content-length": Buffer.byteLength(body),
    });
    res.end(body);
    return;
  }
  res.writeHead(404);
  res.end("not found");
};

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((err) => err ? reject(err) : resolve());
  });
}

function request(port, path) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: "127.0.0.1", port, path }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        resolve({ status: res.statusCode, body });
      });
    });
    req.on("error", reject);
  });
}

async function main() {
  const server = tracer.mount(app, { prefix: "/observability" });
  const port = await listen(server);

  try {
    const chat = await request(port, "/chat");
    if (chat.status !== 200) throw new Error(chat.body);
    if (JSON.parse(chat.body).reply !== "ok") throw new Error(chat.body);

    const dashboard = await request(port, "/observability/");
    if (dashboard.status !== 200) throw new Error(dashboard.body);
    if (!dashboard.body.includes("TraceCast")) throw new Error("dashboard html missing");

    const traces = await request(port, "/observability/api/traces");
    if (traces.status !== 200) throw new Error(traces.body);
    const payload = JSON.parse(traces.body);
    if (payload.traces[0].name !== "node-smoke-chat") throw new Error(traces.body);
    if (payload.traces[0].project_id !== "real-node") throw new Error(traces.body);

    console.log("node-http-smoke ok");
  } finally {
    await close(server);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
