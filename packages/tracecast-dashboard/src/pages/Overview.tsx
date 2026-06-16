import { useState, type ReactNode } from "react";
import { useApi } from "../hooks/useApi";
import { StatCard } from "../components/StatCard";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Legend,
} from "recharts";

const COLORS = ["#c8f751", "#5eead4", "#a78bfa", "#56e29a", "#fbbf24", "#fb7185", "#7dd3fc", "#f0abfc"];
const ACCENT = "#c8f751";
const GRID = "#222734";

const TOOLTIP = {
  background: "#181c25", border: "1px solid #2d3340", borderRadius: 8,
  color: "#e7eaf2", fontSize: 12, fontFamily: "IBM Plex Mono, monospace",
} as const;
const panel = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: "var(--radius)", padding: 20,
} as const;
const panelTitle = {
  fontSize: 11, color: "var(--text-faint)", marginBottom: 18,
  textTransform: "uppercase" as const, letterSpacing: "0.07em", fontWeight: 600,
} as const;

function fmt$(n: number) { return "$" + n.toFixed(4); }
function fmtMs(n: number | null) { return n == null ? "—" : n < 1000 ? `${Math.round(n)}ms` : `${(n / 1000).toFixed(2)}s`; }

interface TokensByModelRow { date: string; model: string; tokens_out: number; cost_usd: number; }

interface Metrics {
  total_traces: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_by_model: Record<string, number>;
  cost_by_project: Record<string, number>;
  traces_over_time: Array<{ date: string; cost_usd: number; traces: number }>;
  tokens_by_model_over_time: TokensByModelRow[];
}

export function PageHead({ title, kicker, children }: { title: string; kicker?: string; children?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 26 }}>
      <div>
        {kicker && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent)", letterSpacing: "0.04em", marginBottom: 6 }}>
            {kicker}
          </div>
        )}
        <h2 style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.025em" }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function PeriodSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        padding: "8px 14px", background: "var(--surface-2)", border: "1px solid var(--border)",
        color: "var(--text)", borderRadius: "var(--radius-sm)", fontSize: 13,
      }}
    >
      <option value="1h">Last hour</option>
      <option value="24h">Last 24h</option>
      <option value="7d">Last 7 days</option>
      <option value="30d">Last 30 days</option>
    </select>
  );
}

/** Pivot [{date, model, tokens_out}] → [{date, [model]: tokens_out}] for Recharts multi-line */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function pivotModelData(rows: TokensByModelRow[]): any[] {
  const map: Record<string, Record<string, unknown>> = {};
  for (const r of rows) {
    if (!map[r.date]) map[r.date] = { date: r.date };
    map[r.date][r.model] = r.tokens_out;
  }
  return Object.values(map).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

export function Overview() {
  const [period, setPeriod] = useState("7d");
  const { data: m, loading, error } = useApi<Metrics>(`/metrics?period=${period}`, [period]);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error || !m) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load metrics"}</div>;

  const projectData = Object.entries(m.cost_by_project).map(([name, value]) => ({ name, value }));
  const modelNames = [...new Set((m.tokens_by_model_over_time ?? []).map((r) => r.model))];
  const modelPivoted = pivotModelData(m.tokens_by_model_over_time ?? []);

  return (
    <div>
      <PageHead title="Overview" kicker="// live telemetry">
        <PeriodSelect value={period} onChange={setPeriod} />
      </PageHead>

      {/* 5 stat cards — cache hit rate removed (not universal) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14, marginBottom: 24 }}>
        <StatCard label="Total Traces" value={m.total_traces.toLocaleString()} accent="#c8f751" />
        <StatCard label="Total Cost" value={fmt$(m.total_cost_usd)} accent="#5eead4" />
        <StatCard label="Avg Latency" value={fmtMs(m.avg_latency_ms)} accent="#a78bfa" />
        <StatCard label="Tokens In" value={m.total_tokens_in.toLocaleString()} accent="#fbbf24" />
        <StatCard label="Tokens Out" value={m.total_tokens_out.toLocaleString()} accent="#7dd3fc" />
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        {/* Cost over time */}
        <div style={{ ...panel, flex: 1.4 }}>
          <h3 style={panelTitle}>Cost Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={m.traces_over_time}>
              <defs>
                <linearGradient id="costLine" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={ACCENT} stopOpacity={0.9} />
                  <stop offset="100%" stopColor={ACCENT} stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ stroke: ACCENT, strokeOpacity: 0.3 }} />
              <Line type="monotone" dataKey="cost_usd" stroke="url(#costLine)" strokeWidth={2.5} dot={false} activeDot={{ r: 4, fill: ACCENT }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Tokens by model over time — replaces the pie chart */}
        <div style={{ ...panel, flex: 1 }}>
          <h3 style={panelTitle}>Tokens Out by Model</h3>
          {modelPivoted.length === 0 ? (
            <div style={{ height: 250, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-faint)", fontFamily: "var(--mono)", fontSize: 12 }}>
              no data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={modelPivoted}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
                <YAxis tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
                <Tooltip contentStyle={TOOLTIP} cursor={{ stroke: "#ffffff22" }} />
                <Legend wrapperStyle={{ color: "var(--text-muted)", fontSize: 11 }} />
                {modelNames.map((model, i) => (
                  <Line key={model} type="monotone" dataKey={model} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {projectData.length > 0 && (
        <div style={panel}>
          <h3 style={panelTitle}>Cost by Project</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={projectData}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-faint)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(200,247,81,0.05)" }} />
              <Bar dataKey="value" fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
