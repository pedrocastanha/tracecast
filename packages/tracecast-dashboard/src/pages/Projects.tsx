import { useApi } from "../hooks/useApi";

interface ProjectSummary {
  project_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

export function Projects() {
  const { data, loading } = useApi<{ projects: ProjectSummary[]; total: number }>("/projects", []);
  if (loading || !data) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Projects</h2>
      <span style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, display: "block" }}>{data.total} projects</span>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Project ID", "Traces", "Cost", "Tokens", "First Trace", "Last Trace"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.projects.map((p) => (
            <tr key={p.project_id}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}><code>{p.project_id}</code></td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{p.trace_count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${p.total_cost_usd.toFixed(4)}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{p.total_tokens.toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(p.first_trace_at).toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(p.last_trace_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
