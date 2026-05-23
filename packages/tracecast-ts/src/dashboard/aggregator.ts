import { Trace, Span, SpanType } from "../types";
import { randomUUID } from "crypto";

export function computeMetrics(
  traces: Trace[],
  opts: {
    period?: string;
    from?: Date;
    to?: Date;
    projectId?: string;
  } = {},
): Record<string, unknown> {
  const now = new Date();
  const delta = periodDelta(opts.period ?? "7d");
  const fromDt = opts.from ?? new Date(now.getTime() - delta);
  const toDt = opts.to ?? now;

  let filtered = traces;
  if (opts.projectId) filtered = filtered.filter(t => t.projectId === opts.projectId);
  filtered = filtered.filter(t => t.startedAt >= fromDt && t.startedAt <= toDt);

  const totalTraces = filtered.length;
  const totalCost = filtered.reduce((s, t) => s + t.costUsd, 0);
  const totalTokensIn = filtered.reduce((s, t) => s + t.totalTokensIn, 0);
  const totalTokensOut = filtered.reduce((s, t) => s + t.totalTokensOut, 0);
  const totalTokensCached = filtered.reduce((s, t) => s + t.totalTokensInCached, 0);
  const avgLatency = totalTraces > 0
    ? filtered.reduce((s, t) => s + (t.latencyMs ?? 0), 0) / totalTraces
    : 0;
  const cacheHitRate = totalTokensIn > 0 ? totalTokensCached / totalTokensIn : 0;

  const costByModel: Record<string, number> = {};
  const costByProject: Record<string, number> = {};
  for (const t of filtered) {
    if (t.model) costByModel[t.model] = (costByModel[t.model] ?? 0) + t.costUsd;
    if (t.projectId) costByProject[t.projectId] = (costByProject[t.projectId] ?? 0) + t.costUsd;
  }

  const tracesOverTime = groupByDay(filtered);

  return {
    period: opts.period ?? "7d",
    total_traces: totalTraces,
    total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
    total_tokens_in: totalTokensIn,
    total_tokens_out: totalTokensOut,
    total_tokens_in_cached: totalTokensCached,
    cache_hit_rate: Math.round(cacheHitRate * 1e4) / 1e4,
    avg_latency_ms: Math.round(avgLatency * 10) / 10,
    cost_by_model: costByModel,
    cost_by_project: costByProject,
    traces_over_time: tracesOverTime,
  };
}

export function paginateTraces(
  traces: Trace[],
  opts: {
    page?: number;
    pageSize?: number;
    sortBy?: string;
    order?: string;
    projectId?: string;
    userId?: string;
    from?: Date;
    to?: Date;
  } = {},
): Record<string, unknown> {
  const page = opts.page ?? 1;
  const pageSize = opts.pageSize ?? 50;

  let filtered = traces;
  if (opts.projectId) filtered = filtered.filter(t => t.projectId === opts.projectId);
  if (opts.userId) filtered = filtered.filter(t => t.userId === opts.userId);
  if (opts.from) filtered = filtered.filter(t => t.startedAt >= opts.from!);
  if (opts.to) filtered = filtered.filter(t => t.startedAt <= opts.to!);

  const sortBy = opts.sortBy ?? "date";
  const order = opts.order ?? "desc";
  const keyFn: Record<string, (t: Trace) => number> = {
    cost: (t) => t.costUsd,
    duration: (t) => t.latencyMs ?? 0,
    tokens: (t) => t.totalTokens,
    date: (t) => t.startedAt.getTime(),
  };
  const key = keyFn[sortBy] ?? keyFn.date;
  filtered.sort((a, b) => {
    return (order === "desc" ? -1 : 1) * (key(a) - key(b));
  });

  const total = filtered.length;
  const start = (page - 1) * pageSize;
  const items = filtered.slice(start, start + pageSize);

  return {
    traces: items.map(traceSummary),
    total,
    page,
    page_size: pageSize,
  };
}

function traceSummary(t: Trace): Record<string, unknown> {
  return {
    trace_id: t.traceId,
    name: t.name,
    project_id: t.projectId,
    user_id: t.userId,
    session_id: t.sessionId,
    model: t.model,
    started_at: t.startedAt.toISOString(),
    finished_at: t.finishedAt?.toISOString() ?? null,
    latency_ms: t.latencyMs,
    total_tokens_in: t.totalTokensIn,
    total_tokens_out: t.totalTokensOut,
    total_tokens_in_cached: t.totalTokensInCached,
    total_tokens: t.totalTokens,
    cost_usd: t.costUsd,
    span_count: t.spans.length,
    tools_used: t.toolsUsed,
  };
}

function periodDelta(period: string): number {
  const map: Record<string, number> = { "1h": 3600000, "24h": 86400000, "7d": 604800000, "30d": 2592000000 };
  return map[period] ?? 604800000;
}

function groupByDay(traces: Trace[]): Array<{ date: string; traces: number; cost_usd: number }> {
  const groups: Record<string, { date: string; traces: number; cost_usd: number }> = {};
  for (const t of traces) {
    const day = t.startedAt.toISOString().slice(0, 10);
    if (!groups[day]) groups[day] = { date: day, traces: 0, cost_usd: 0 };
    groups[day].traces++;
    groups[day].cost_usd += t.costUsd;
  }
  return Object.values(groups).sort((a, b) => a.date.localeCompare(b.date));
}
