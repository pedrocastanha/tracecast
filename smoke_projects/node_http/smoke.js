const http = require("http");
const { DictExporter, Tracer, setDefaultTracer, traceCast, wrapOpenAI } = require("tracecast");

const exporter = new DictExporter();
const client = wrapOpenAI({
  chat: {
    completions: {
      create: async (kwargs) => ({
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
const runChat = traceCast(async () => {
  const response = await client.chat.completions.create({
    model: "gpt-4o",
    messages: [{ role: "user", content: "hello" }],
  });
  return { reply: response.choices[0].message.content };
}, {
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
    const trace = payload.traces[0];
    if (trace.name !== "node-smoke-chat") throw new Error(traces.body);
    if (trace.project_id !== "real-node") throw new Error(traces.body);
    if (trace.total_tokens_in !== 90) throw new Error(traces.body);
    if (trace.total_tokens_out !== 30) throw new Error(traces.body);
    if (trace.total_tokens_in_cached !== 20) throw new Error(traces.body);
    if (trace.total_tokens !== 120) throw new Error(traces.body);

    console.log("node-http-smoke ok");
  } finally {
    await close(server);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
