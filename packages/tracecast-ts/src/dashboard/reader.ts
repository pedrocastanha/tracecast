import { Trace, Span, SpanType } from "../types";
import { readFile } from "fs/promises";
import { BaseExporter } from "../exporters/base";

export class TraceReader {
  private exporters: BaseExporter[];
  private maxTraces: number;
  private cache: Trace[] | null = null;
  private cacheTtl = 5000;
  private lastRead = 0;

  constructor(exporters: BaseExporter[], maxTraces = 500) {
    this.exporters = exporters;
    this.maxTraces = maxTraces;
  }

  async getTraces(): Promise<Trace[]> {
    const now = Date.now();
    if (this.cache !== null && (now - this.lastRead) < this.cacheTtl) {
      return this.cache;
    }

    const traces: Trace[] = [];
    for (const exporter of this.exporters) {
      const fromExp = await this.readFrom(exporter);
      traces.push(...fromExp);
    }

    traces.sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime());
    if (traces.length > this.maxTraces) {
      traces.length = this.maxTraces;
    }

    this.cache = traces;
    this.lastRead = now;
    return traces;
  }

  async getTrace(traceId: string): Promise<Trace | null> {
    for (const t of await this.getTraces()) {
      if (t.traceId === traceId) return t;
    }
    return null;
  }

  private async readFrom(exporter: BaseExporter): Promise<Trace[]> {
    const name = exporter.constructor.name;

    if (name.includes("DictExporter")) {
      const raw = (exporter as any).traces ?? [];
      return raw.filter((d: any) => typeof d === "object").map(hydrateTrace);
    }

    if (name.includes("JsonFile")) {
      const path = (exporter as any).path;
      if (!path) return [];
      try {
        const content = await readFile(path, "utf-8");
        return content.split("\n").filter(Boolean).map((line: string) => {
          try { return hydrateTrace(JSON.parse(line)); }
          catch { return null; }
        }).filter(Boolean) as Trace[];
      } catch {
        return [];
      }
    }

    return [];
  }
}

function hydrateTrace(d: Record<string, unknown>): Trace {
  const spans: Span[] = ((d.spans as any[]) ?? (d.Spans as any[]) ?? []).map((s: any) => ({
    spanId: s.span_id ?? s.spanId ?? "",
    type: (s.type ?? "llm") as SpanType,
    name: s.name ?? "",
    startedAt: new Date(s.started_at ?? s.startedAt ?? Date.now()),
    finishedAt: s.finished_at ? new Date(s.finished_at) : s.finishedAt ? new Date(s.finishedAt) : undefined,
    model: s.model,
    tokensIn: s.tokens_in ?? s.tokensIn ?? 0,
    tokensOut: s.tokens_out ?? s.tokensOut ?? 0,
    tokensInCached: s.tokens_in_cached ?? s.tokensInCached ?? 0,
    costUsd: s.cost_usd ?? s.costUsd ?? 0,
    metadata: (s.metadata ?? {}) as Record<string, unknown>,
  }));

  return {
    traceId: (d.trace_id ?? d.traceId ?? "") as string,
    name: (d.name ?? "unknown") as string,
    startedAt: new Date((d.started_at ?? d.startedAt ?? Date.now()) as string),
    finishedAt: (d.finished_at ?? d.finishedAt) ? new Date((d.finished_at ?? d.finishedAt) as string) : undefined,
    sessionId: (d.session_id ?? d.sessionId) as string | undefined,
    userId: (d.user_id ?? d.userId) as string | undefined,
    projectId: (d.project_id ?? d.projectId) as string | undefined,
    model: (d.model) as string | undefined,
    totalTokensIn: (d.total_tokens_in ?? d.totalTokensIn ?? 0) as number,
    totalTokensOut: (d.total_tokens_out ?? d.totalTokensOut ?? 0) as number,
    totalTokensInCached: (d.total_tokens_in_cached ?? d.totalTokensInCached ?? 0) as number,
    totalTokens: (d.total_tokens ?? d.totalTokens ?? 0) as number,
    costUsd: (d.cost_usd ?? d.costUsd ?? 0) as number,
    latencyMs: (d.latency_ms ?? d.latencyMs) as number | undefined,
    toolsUsed: (d.tools_used ?? d.toolsUsed ?? {}) as Record<string, number>,
    spans,
    metadata: (d.metadata ?? {}) as Record<string, unknown>,
  };
}
