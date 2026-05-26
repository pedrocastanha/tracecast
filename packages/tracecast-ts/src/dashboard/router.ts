import { IncomingMessage, ServerResponse } from "http";
import { TraceReader } from "./reader";
import { computeMetrics, paginateTraces } from "./aggregator";
import { Trace } from "../types";
import path from "path";
import fs from "fs";

const STATIC_DIR = path.join(__dirname, "static");

export type DashboardHandler = (req: IncomingMessage, res: ServerResponse, next?: () => void) => void;

function traceSummary(t: Trace) {
  return {
    traceId: t.traceId,
    name: t.name,
    startedAt: t.startedAt.toISOString(),
    finishedAt: t.finishedAt?.toISOString() ?? null,
    costUsd: t.costUsd,
    totalTokens: t.totalTokens,
    latencyMs: t.latencyMs,
    spanCount: t.spans.length,
  };
}

function one(val: string | null): string | undefined {
  return val === null ? undefined : val;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

function sendText(res: ServerResponse, status: number, body: string, contentType = "text/plain; charset=utf-8"): void {
  res.writeHead(status, {
    "content-type": contentType,
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function mime(filename: string): string {
  if (filename.endsWith(".html")) return "text/html; charset=utf-8";
  if (filename.endsWith(".css")) return "text/css; charset=utf-8";
  if (filename.endsWith(".js")) return "application/javascript; charset=utf-8";
  if (filename.endsWith(".svg")) return "image/svg+xml";
  if (filename.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

function sendFile(res: ServerResponse, filePath: string): void {
  const content = fs.readFileSync(filePath);
  res.writeHead(200, {
    "content-type": mime(filePath),
    "content-length": content.length,
  });
  res.end(content);
}

function staticPath(...parts: string[]): string | null {
  const fp = path.resolve(STATIC_DIR, ...parts);
  if (!fp.startsWith(STATIC_DIR + path.sep) && fp !== STATIC_DIR) return null;
  return fp;
}

function parseRequest(req: IncomingMessage): URL {
  return new URL(req.url ?? "/", "http://tracecast.local");
}

export function createRouter(reader: TraceReader): DashboardHandler {
  return (req: IncomingMessage, res: ServerResponse) => {
    void handleRequest(reader, req, res);
  };
}

async function handleRequest(reader: TraceReader, req: IncomingMessage, res: ServerResponse): Promise<void> {
  try {
    if ((req.method ?? "GET") !== "GET") {
      sendJson(res, 405, { error: "Method not allowed" });
      return;
    }

    const url = parseRequest(req);
    const requestPath = url.pathname.replace(/\/+$/, "") || "/";
    const segments = requestPath.split("/").filter(Boolean).map(decodeURIComponent);

    if (requestPath === "/api/traces") {
      const page = parseInt(one(url.searchParams.get("page")) ?? "1");
      const pageSize = parseInt(one(url.searchParams.get("page_size")) ?? "50");
      const from = one(url.searchParams.get("from")) ? new Date(one(url.searchParams.get("from"))!) : undefined;
      const to = one(url.searchParams.get("to")) ? new Date(one(url.searchParams.get("to"))!) : undefined;
      const traces = await reader.getTraces();
      sendJson(res, 200, paginateTraces(traces, {
        page,
        pageSize,
        projectId: one(url.searchParams.get("project_id")),
        userId: one(url.searchParams.get("user_id")),
        from,
        to,
        sortBy: one(url.searchParams.get("sort_by")) ?? "date",
        order: one(url.searchParams.get("order")) ?? "desc",
      }));
      return;
    }

    if (segments[0] === "api" && segments[1] === "traces" && segments[2]) {
      const trace = await reader.getTrace(segments[2]);
      if (!trace) sendJson(res, 404, { error: "Trace not found" });
      else sendJson(res, 200, trace);
      return;
    }

    if (requestPath === "/api/metrics") {
      const from = one(url.searchParams.get("from")) ? new Date(one(url.searchParams.get("from"))!) : undefined;
      const to = one(url.searchParams.get("to")) ? new Date(one(url.searchParams.get("to"))!) : undefined;
      const traces = await reader.getTraces();
      sendJson(res, 200, computeMetrics(traces, {
        period: one(url.searchParams.get("period")) ?? "7d",
        from,
        to,
        projectId: one(url.searchParams.get("project_id")),
      }));
      return;
    }

    if (requestPath === "/api/sessions") {
      const sessions = await reader.getSessions();
      sendJson(res, 200, { sessions, total: sessions.length });
      return;
    }

    if (segments[0] === "api" && segments[1] === "sessions" && segments[2]) {
      const traces = await reader.getSession(segments[2]);
      if (!traces.length) {
        sendJson(res, 404, { error: "Session not found" });
        return;
      }
      sendJson(res, 200, {
        session_id: segments[2],
        traces: traces.map(traceSummary),
        total_cost_usd: Math.round(traces.reduce((s, t) => s + t.costUsd, 0) * 1e6) / 1e6,
        total_tokens: traces.reduce((s, t) => s + t.totalTokens, 0),
      });
      return;
    }

    if (requestPath === "/api/projects") {
      const projects = await reader.getProjects();
      sendJson(res, 200, { projects, total: projects.length });
      return;
    }

    if (segments[0] === "api" && segments[1] === "projects" && segments[2]) {
      const traces = await reader.getProject(segments[2]);
      if (!traces.length) {
        sendJson(res, 404, { error: "Project not found" });
        return;
      }
      sendJson(res, 200, {
        project_id: segments[2],
        traces: traces.map(traceSummary),
        total_cost_usd: Math.round(traces.reduce((s, t) => s + t.costUsd, 0) * 1e6) / 1e6,
        total_tokens: traces.reduce((s, t) => s + t.totalTokens, 0),
      });
      return;
    }

    if (requestPath === "/api/health") {
      sendJson(res, 200, { status: "ok", version: "0.3.0" });
      return;
    }

    if (segments[0] === "static" && segments[1]) {
      const fp = staticPath(segments[1]);
      if (!fp) {
        sendText(res, 400, "Invalid path");
      } else if (fs.existsSync(fp)) {
        sendFile(res, fp);
      } else {
        sendText(res, 404, "Not found");
      }
      return;
    }

    if (segments[0] === "assets" && segments.length > 1) {
      const fp = staticPath("assets", ...segments.slice(1));
      if (!fp) {
        sendText(res, 400, "Invalid path");
      } else if (fs.existsSync(fp)) {
        sendFile(res, fp);
      } else {
        sendText(res, 404, "Not found");
      }
      return;
    }

    if (segments[0] === "api") {
      sendJson(res, 404, { error: "Not found" });
      return;
    }

    const indexPath = path.join(STATIC_DIR, "index.html");
    if (fs.existsSync(indexPath)) {
      sendFile(res, indexPath);
    } else {
      sendText(res, 200, "<h1>TraceCast Dashboard</h1>", "text/html; charset=utf-8");
    }
  } catch (err: any) {
    sendJson(res, 500, { error: err?.message ?? String(err) });
  }
}
