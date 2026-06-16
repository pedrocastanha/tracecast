import { useState, type ReactNode } from "react";
import { useApi } from "../hooks/useApi";
import { StatCard } from "../components/StatCard";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Legend } from "recharts";

// Cohesive signal palette (lime-led), shared across all charts.
const COLORS = ["#c8f751", "#5eead4", "#a78bfa", "#56e29a", "#fbbf24", "#fb7185", "#7dd3fc", "#f0abfc"];
const ACCENT = "#c8f751";
const GRID = "#222734";

const TOOLTIP = { background: "#181c25", border: "1px solid #2d3340", borderRadius: 8, color: "#e7eaf2", fontSize: 12, fontFamily: "IBM Plex Mono, monospace" } as const;
const panel = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 20 } as const;
const panelTitle = { fontSize: 11, color: "var(--text-faint)", marginBottom: 18, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 } as const;

function fmt$(n: number) { return "$" + n.toFixed(4); }
function fmtMs(n: number | null) { return n == null ? "—" : n < 1000 ? `${Math.round(n)}ms` : `${(n / 1000).toFixed(2)}s`; }
function fmtPct(n: number) { return (n * 100).toFixed(1) + "%"; }

interface Metrics {
  total_traces: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  cache_hit_rate: number;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_by_model: Record<string, number>;
  cost_by_project: Record<string, number>;
  traces_over_time: Array<{ date: string; cost_usd: number; traces: number }>;
}

export function PageHead({ title, kicker, children }: { title: string; kicker?: string; children?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 26 }}>
      <div>
        {kicker && <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent)", letterSpacing: "0.04em", marginBottom: 6 }}>{kicker}</div>}
        <h2 style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.025em" }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function PeriodSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      style={{ padding: "8px 14px", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: "var(--radius-sm)", fontSize: 13 }}>
      <option value="1h">Last hour</option>
      <option value="24h">Last 24h</option>
      <option value="7d">Last 7 days</option>
      <option value="30d">Last 30 days</option>
    </select>
  );
}

export function Overview() {
  const [period, setPeriod] = useState("7d");
  const { data: m, loading, error } = useApi<Metrics>(`/metrics?period=${period}`, [period]);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error || !m) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load metrics"}</div>;

  const modelData = Object.entries(m.cost_by_model).map(([name, value]) => ({ name, value }));
  const projectData = Object.entries(m.cost_by_project).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <PageHead title="Overview" kicker="// live telemetry">
        <PeriodSelect value={period} onChange={setPeriod} />
      </PageHead>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 14, marginBottom: 24 }}>
        <StatCard label="Total Traces" value={m.total_traces.toLocaleString()} accent="#c8f751" />
        <StatCard label="Total Cost" value={fmt$(m.total_cost_usd)} accent="#5eead4" />
        <StatCard label="Avg Latency" value={fmtMs(m.avg_latency_ms)} accent="#a78bfa" />
        <StatCard label="Cache Hit Rate" value={fmtPct(m.cache_hit_rate)} accent="#56e29a" />
        <StatCard label="Tokens In" value={m.total_tokens_in.toLocaleString()} accent="#fbbf24" />
        <StatCard label="Tokens Out" value={m.total_tokens_out.toLocaleString()} accent="#7dd3fc" />
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
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
        <div style={{ ...panel, flex: 1 }}>
          <h3 style={panelTitle}>Cost by Model</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={modelData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={48} outerRadius={82} paddingAngle={2} stroke="#13161e" strokeWidth={2}>
                {modelData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={TOOLTIP} />
              <Legend wrapperStyle={{ color: "var(--text-muted)", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
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
