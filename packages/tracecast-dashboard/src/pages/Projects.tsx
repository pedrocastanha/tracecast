import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { PageHead } from "./Overview";

interface ProjectSummary {
  project_name?: string;
  project_id?: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

interface SubProject {
  project_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

const td = { padding: "12px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" } as const;
const mono = { ...td, fontFamily: "var(--mono)", color: "var(--text-muted)" } as const;

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <span style={{ display: "inline-block", transition: "transform 0.15s", transform: open ? "rotate(90deg)" : "rotate(0deg)", fontSize: 11, color: "var(--text-faint)", marginLeft: 6 }}>
      ▶
    </span>
  );
}

function SubProjectsRow({ projectName }: { projectName: string }) {
  const { data, loading } = useApi<{ sub_projects: SubProject[] }>(
    `/projects/${encodeURIComponent(projectName)}/sub-projects`,
    [projectName],
  );

  if (loading) {
    return (
      <tr>
        <td colSpan={6} style={{ ...td, paddingLeft: 36, background: "var(--bg-2)", color: "var(--text-faint)", fontFamily: "var(--mono)", fontSize: 12 }}>
          Loading…
        </td>
      </tr>
    );
  }

  if (!data || data.sub_projects.length === 0) {
    return (
      <tr>
        <td colSpan={6} style={{ ...td, paddingLeft: 36, background: "var(--bg-2)", color: "var(--text-faint)", fontFamily: "var(--mono)", fontSize: 12 }}>
          No filials found
        </td>
      </tr>
    );
  }

  return (
    <>
      {data.sub_projects.map((sp) => (
        <tr
          key={sp.project_id}
          style={{ background: "var(--bg-2)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--bg-2)")}
        >
          <td style={{ ...td, paddingLeft: 36, borderBottom: "1px solid var(--border)" }}>
            <code style={{ fontSize: 11, color: "var(--text-muted)" }}>{sp.project_id}</code>
          </td>
          <td style={{ ...mono, fontFamily: "var(--mono)", fontSize: 12 }}>{sp.trace_count}</td>
          <td style={{ ...mono, color: "var(--accent)", fontSize: 12 }}>${sp.total_cost_usd.toFixed(4)}</td>
          <td style={{ ...mono, fontSize: 12 }}>{sp.total_tokens.toLocaleString()}</td>
          <td style={{ ...mono, fontSize: 12 }}>{new Date(sp.first_trace_at).toLocaleString()}</td>
          <td style={{ ...mono, fontSize: 12 }}>{new Date(sp.last_trace_at).toLocaleString()}</td>
        </tr>
      ))}
    </>
  );
}

export function Projects() {
  const { data, loading, error } = useApi<{ projects: ProjectSummary[]; total: number }>("/projects", []);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error || !data) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load projects"}</div>;

  const hasProjectNames = data.projects.some((p) => p.project_name);

  return (
    <div>
      <PageHead title="Projects" kicker={`// ${data.total} tracked`} />
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {[hasProjectNames ? "App" : "Project ID", "Traces", "Cost", "Tokens", "First Trace", "Last Trace"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "12px 14px", borderBottom: "1px solid var(--border)", fontSize: 12, color: "var(--text-faint)", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.projects.map((p) => {
              const key = p.project_name ?? p.project_id ?? "";
              const isExpanded = expanded === key;
              const canDrillDown = !!p.project_name;

              return (
                <>
                  <tr
                    key={key}
                    onClick={() => canDrillDown && setExpanded(isExpanded ? null : key)}
                    style={{ cursor: canDrillDown ? "pointer" : "default" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                  >
                    <td style={{ ...td, fontWeight: 600 }}>
                      {p.project_name ? (
                        <>
                          <span style={{ color: "var(--accent)" }}>{p.project_name}</span>
                          <ChevronIcon open={isExpanded} />
                        </>
                      ) : (
                        <code>{p.project_id}</code>
                      )}
                    </td>
                    <td style={mono}>{p.trace_count}</td>
                    <td style={{ ...mono, color: "var(--accent)" }}>${p.total_cost_usd.toFixed(4)}</td>
                    <td style={mono}>{p.total_tokens.toLocaleString()}</td>
                    <td style={mono}>{new Date(p.first_trace_at).toLocaleString()}</td>
                    <td style={mono}>{new Date(p.last_trace_at).toLocaleString()}</td>
                  </tr>
                  {isExpanded && p.project_name && (
                    <SubProjectsRow key={`${key}-sub`} projectName={p.project_name} />
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
