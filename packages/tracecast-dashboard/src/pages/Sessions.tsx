import { useApi } from "../hooks/useApi";

interface SessionSummary {
  session_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

export function Sessions() {
  const { data, loading, error } = useApi<{ sessions: SessionSummary[]; total: number }>("/sessions", []);
  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error || !data) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load sessions"}</div>;
  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Sessions</h2>
      <span style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, display: "block" }}>{data.total} sessions</span>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Session ID", "Traces", "Cost", "Tokens", "First Trace", "Last Trace"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.sessions.map((s) => (
            <tr key={s.session_id}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}><code>{s.session_id}</code></td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{s.trace_count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${s.total_cost_usd.toFixed(4)}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{s.total_tokens.toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(s.first_trace_at).toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(s.last_trace_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
