import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { PageHead, PeriodSelect } from "./Overview";
import { CascadeFilter, type CascadeFilterValue } from "../components/CascadeFilter";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const ACCENT = "#c8f751";
const GRID = "#222734";
const TOOLTIP = { background: "#181c25", border: "1px solid #2d3340", borderRadius: 8, color: "#e7eaf2", fontSize: 12, fontFamily: "IBM Plex Mono, monospace" } as const;
const td = { padding: "11px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" } as const;

interface ModelBreakdown {
  calls: number;
  total_tokens: number;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_usd: number;
}

export function Models() {
  const [period, setPeriod] = useState("7d");
  const [filter, setFilter] = useState<CascadeFilterValue>({ projectName: "", projectId: "", userId: "" });
  const metricsParams = `/metrics?period=${period}` +
    (filter.projectName ? `&project_name=${encodeURIComponent(filter.projectName)}` : "") +
    (filter.projectId   ? `&project_id=${encodeURIComponent(filter.projectId)}`     : "");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: m, loading } = useApi<any>(metricsParams, [period, filter.projectName, filter.projectId]);

  if (loading || !m) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;

  const costData = Object.entries(m.cost_by_model || {}).map(([name, value]) => ({ name, cost: value as number }));
  const modelBreakdown: Record<string, ModelBreakdown> = m.models_breakdown || {};

  return (
    <div>
      <PageHead title="Models" kicker="// cost & usage">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <CascadeFilter value={filter} onChange={setFilter} />
          <PeriodSelect value={period} onChange={setPeriod} />
        </div>
      </PageHead>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 20, marginBottom: 24 }}>
        <h3 style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 18, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Cost per Model</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={costData}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
            <YAxis tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(200,247,81,0.05)" }} formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]} />
            <Bar dataKey="cost" fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={56} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Model", "LLM Calls", "Tokens In", "Tokens Out", "Cost"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(modelBreakdown)
              .sort(([, a], [, b]) => b.total_tokens - a.total_tokens)
              .map(([model, stats]) => (
                <tr key={model}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
                  <td style={td}><code>{model}</code></td>
                  <td style={{ ...td, fontFamily: "var(--mono)" }}>{stats.calls.toLocaleString()}</td>
                  <td style={{ ...td, fontFamily: "var(--mono)" }}>{stats.total_tokens_in.toLocaleString()}</td>
                  <td style={{ ...td, fontFamily: "var(--mono)" }}>{stats.total_tokens_out.toLocaleString()}</td>
                  <td style={{ ...td, fontFamily: "var(--mono)" }}>${stats.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
