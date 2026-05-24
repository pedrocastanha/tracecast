import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { StatCard } from "../components/StatCard";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Legend } from "recharts";

const COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#a855f7", "#ec4899", "#84cc16"];

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

export function Overview() {
  const [period, setPeriod] = useState("7d");
  const { data: m, loading, error } = useApi<Metrics>(`/metrics?period=${period}`, [period]);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error || !m) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load metrics"}</div>;

  const modelData = Object.entries(m.cost_by_model).map(([name, value]) => ({ name, value }));
  const projectData = Object.entries(m.cost_by_project).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Overview</h2>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }}>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 16, marginBottom: 24 }}>
        <StatCard label="Total Traces" value={m.total_traces.toLocaleString()} />
        <StatCard label="Total Cost" value={fmt$(m.total_cost_usd)} />
        <StatCard label="Avg Latency" value={fmtMs(m.avg_latency_ms)} />
        <StatCard label="Cache Hit Rate" value={fmtPct(m.cache_hit_rate)} />
        <StatCard label="Tokens In" value={m.total_tokens_in.toLocaleString()} />
        <StatCard label="Tokens Out" value={m.total_tokens_out.toLocaleString()} />
      </div>

      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <div style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={m.traces_over_time}>
              <CartesianGrid stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Line type="monotone" dataKey="cost_usd" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost by Model</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={modelData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                {modelData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Legend wrapperStyle={{ color: "var(--text-muted)", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {projectData.length > 0 && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost by Project</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={projectData}>
              <CartesianGrid stroke="var(--border)" />
              <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Bar dataKey="value" fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
