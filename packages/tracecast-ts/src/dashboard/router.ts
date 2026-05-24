import express, { Router, Request, Response } from "express";
import { TraceReader } from "./reader";
import { computeMetrics, paginateTraces } from "./aggregator";
import { Trace } from "../types";
import path from "path";
import fs from "fs";

const STATIC_DIR = path.join(__dirname, "static");

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

function qs(val: any): string | undefined {
  if (typeof val === "string") return val;
  if (Array.isArray(val)) return val[0];
  return undefined;
}

export function createRouter(reader: TraceReader): Router {
  const router = Router();

  router.use(express.json());

  router.get("/api/traces", (req: Request, res: Response) => {
    try {
      const page = parseInt(qs(req.query.page) || "1");
      const pageSize = parseInt(qs(req.query.page_size) || "50");
      const from = qs(req.query.from) ? new Date(qs(req.query.from)!) : undefined;
      const to = qs(req.query.to) ? new Date(qs(req.query.to)!) : undefined;

      reader.getTraces().then(traces => {
        const result = paginateTraces(traces, {
          page, pageSize,
          projectId: qs(req.query.project_id),
          userId: qs(req.query.user_id),
          from, to,
          sortBy: qs(req.query.sort_by) ?? "date",
          order: qs(req.query.order) ?? "desc",
        });
        res.json(result);
      }).catch(err => {
        res.status(500).json({ error: err.message });
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  router.get("/api/traces/:traceId", (req: Request, res: Response) => {
    reader.getTrace(qs(req.params.traceId)!).then(trace => {
      if (!trace) return res.status(404).json({ error: "Trace not found" });
      res.json(trace);
    }).catch(err => {
      res.status(500).json({ error: err.message });
    });
  });

  router.get("/api/metrics", (req: Request, res: Response) => {
    const from = qs(req.query.from) ? new Date(qs(req.query.from)!) : undefined;
    const to = qs(req.query.to) ? new Date(qs(req.query.to)!) : undefined;

    reader.getTraces().then(traces => {
      const result = computeMetrics(traces, {
        period: qs(req.query.period) ?? "7d",
        from, to,
        projectId: qs(req.query.project_id) as string,
      });
      res.json(result);
    }).catch(err => {
      res.status(500).json({ error: err.message });
    });
  });

  router.get("/api/sessions", (_req: Request, res: Response) => {
    reader.getSessions()
      .then(sessions => res.json({ sessions, total: sessions.length }))
      .catch(err => res.status(500).json({ error: err.message }));
  });

  router.get("/api/sessions/:sessionId", (req: Request, res: Response) => {
    reader.getSession(qs(req.params.sessionId)!).then(traces => {
      if (!traces.length) return res.status(404).json({ error: "Session not found" });
      const totalCost = traces.reduce((s, t) => s + t.costUsd, 0);
      const totalTokens = traces.reduce((s, t) => s + t.totalTokens, 0);
      res.json({
        session_id: req.params.sessionId,
        traces: traces.map(traceSummary),
        total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
        total_tokens: totalTokens,
      });
    }).catch(err => res.status(500).json({ error: err.message }));
  });

  router.get("/api/projects", (_req: Request, res: Response) => {
    reader.getProjects()
      .then(projects => res.json({ projects, total: projects.length }))
      .catch(err => res.status(500).json({ error: err.message }));
  });

  router.get("/api/projects/:projectId", (req: Request, res: Response) => {
    reader.getProject(qs(req.params.projectId)!).then(traces => {
      if (!traces.length) return res.status(404).json({ error: "Project not found" });
      const totalCost = traces.reduce((s, t) => s + t.costUsd, 0);
      const totalTokens = traces.reduce((s, t) => s + t.totalTokens, 0);
      res.json({
        project_id: req.params.projectId,
        traces: traces.map(traceSummary),
        total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
        total_tokens: totalTokens,
      });
    }).catch(err => res.status(500).json({ error: err.message }));
  });

  router.get("/api/health", (_req: Request, res: Response) => {
    res.json({ status: "ok", version: "0.3.0" });
  });

  router.get("/", (_req: Request, res: Response) => {
    const indexPath = path.join(STATIC_DIR, "index.html");
    if (fs.existsSync(indexPath)) {
      res.sendFile(indexPath);
    } else {
      res.send("<h1>TraceCast Dashboard</h1>");
    }
  });

  router.get("/static/:filename", (req: Request, res: Response) => {
    const fp = path.resolve(STATIC_DIR, qs(req.params.filename)!);
    if (!fp.startsWith(STATIC_DIR + path.sep) && fp !== STATIC_DIR) {
      return res.status(400).send("Invalid path");
    }
    if (fs.existsSync(fp)) {
      res.sendFile(fp);
    } else {
      res.status(404).send("Not found");
    }
  });

  return router;
}
