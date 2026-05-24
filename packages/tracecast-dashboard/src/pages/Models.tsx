import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function Models() {
  const [period, setPeriod] = useState("7d");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: m, loading } = useApi<any>(`/metrics?period=${period}`, [period]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: traces } = useApi<any>("/traces?page=1&page_size=200", []);

  if (loading || !m) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  const costData = Object.entries(m.cost_by_model || {}).map(([name, value]) => ({ name, cost: value as number }));

  const modelStats: Record<string, { count: number; tokens: number }> = {};
  for (const t of (traces?.traces ?? [])) {
    if (!t.model) continue;
    if (!modelStats[t.model]) modelStats[t.model] = { count: 0, tokens: 0 };
    modelStats[t.model].count++;
    modelStats[t.model].tokens += t.total_tokens ?? 0;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Models</h2>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }}>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20, marginBottom: 24 }}>
        <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost per Model</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={costData}>
            <CartesianGrid stroke="var(--border)" />
            <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
            <Bar dataKey="cost" fill="#6366f1" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Model", "Traces", "Total Tokens"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(modelStats).sort(([, a], [, b]) => b.count - a.count).map(([model, stats]) => (
            <tr key={model}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{model}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{stats.count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{stats.tokens.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
