import { useApi } from "../hooks/useApi";
import { PageHead } from "./Overview";

interface ProjectSummary {
  project_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

const td = { padding: "12px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" } as const;
const mono = { ...td, fontFamily: "var(--mono)", color: "var(--text-muted)" } as const;

export function Projects() {
  const { data, loading, error } = useApi<{ projects: ProjectSummary[]; total: number }>("/projects", []);
  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error || !data) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load projects"}</div>;
  return (
    <div>
      <PageHead title="Projects" kicker={`// ${data.total} tracked`} />
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Project ID", "Traces", "Cost", "Tokens", "First Trace", "Last Trace"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.projects.map((p) => (
              <tr key={p.project_id}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
                <td style={td}><code>{p.project_id}</code></td>
                <td style={mono}>{p.trace_count}</td>
                <td style={{ ...mono, color: "var(--accent)" }}>${p.total_cost_usd.toFixed(4)}</td>
                <td style={mono}>{p.total_tokens.toLocaleString()}</td>
                <td style={mono}>{new Date(p.first_trace_at).toLocaleString()}</td>
                <td style={mono}>{new Date(p.last_trace_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
