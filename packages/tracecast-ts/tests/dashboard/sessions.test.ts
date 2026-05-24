import { computeSessions, computeProjects } from "../../src/dashboard/aggregator";

function makeTrace(id: string, sessionId?: string, projectId?: string, cost = 0.01): any {
  return {
    traceId: id,
    name: `trace-${id}`,
    startedAt: new Date("2026-05-20T10:00:00Z"),
    finishedAt: new Date("2026-05-20T10:01:00Z"),
    totalTokensIn: 100,
    totalTokensOut: 50,
    totalTokensInCached: 0,
    totalTokens: 150,
    costUsd: cost,
    latencyMs: 60000,
    toolsUsed: {},
    spans: [],
    metadata: {},
    sessionId,
    projectId,
  };
}

describe("computeSessions", () => {
  it("groups traces by sessionId", () => {
    const traces = [
      makeTrace("t1", "s1", undefined, 0.01),
      makeTrace("t2", "s1", undefined, 0.02),
      makeTrace("t3", "s2", undefined, 0.05),
    ];
    const sessions = computeSessions(traces);
    expect(sessions).toHaveLength(2);
    const s1 = sessions.find((s: any) => s.session_id === "s1")!;
    expect(s1.trace_count).toBe(2);
    expect((s1.total_cost_usd as number)).toBeCloseTo(0.03, 4);
    expect(s1.total_tokens).toBe(300);
  });

  it("ignores traces without sessionId", () => {
    const traces = [makeTrace("t1"), makeTrace("t2", "s1")];
    const sessions = computeSessions(traces);
    expect(sessions).toHaveLength(1);
  });

  it("returns empty array when no sessions", () => {
    expect(computeSessions([])).toHaveLength(0);
    expect(computeSessions([makeTrace("t1")])).toHaveLength(0);
  });

  it("tracks first and last trace timestamps correctly", () => {
    const traces = [
      { ...makeTrace("t1", "s1"), startedAt: new Date("2026-05-20T08:00:00Z") },
      { ...makeTrace("t2", "s1"), startedAt: new Date("2026-05-20T10:00:00Z") },
      { ...makeTrace("t3", "s1"), startedAt: new Date("2026-05-20T09:00:00Z") },
    ];
    const sessions = computeSessions(traces);
    expect(sessions).toHaveLength(1);
    const s = sessions[0] as any;
    expect(s.first_trace_at).toBe("2026-05-20T08:00:00.000Z");
    expect(s.last_trace_at).toBe("2026-05-20T10:00:00.000Z");
  });
});

describe("computeProjects", () => {
  it("groups traces by projectId", () => {
    const traces = [
      makeTrace("t1", undefined, "p1", 0.01),
      makeTrace("t2", undefined, "p1", 0.02),
      makeTrace("t3", undefined, "p2", 0.05),
    ];
    const projects = computeProjects(traces);
    expect(projects).toHaveLength(2);
    const p1 = projects.find((p: any) => p.project_id === "p1")!;
    expect(p1.trace_count).toBe(2);
    expect((p1.total_cost_usd as number)).toBeCloseTo(0.03, 4);
  });

  it("ignores traces without projectId", () => {
    const traces = [makeTrace("t1"), makeTrace("t2", undefined, "p1")];
    const projects = computeProjects(traces);
    expect(projects).toHaveLength(1);
  });
});
