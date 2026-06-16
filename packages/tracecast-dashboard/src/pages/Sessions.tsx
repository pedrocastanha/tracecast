import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { PageHead } from "./Overview";

interface SessionSummary {
  session_id: string;
  project_name: string | null;
  project_id: string | null;
  user_id: string | null;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  first_trace_at: string;
  last_trace_at: string;
}

interface FilterOptions {
  project_names: string[];
  project_ids: Record<string, string[]>;
  user_ids: Record<string, string[]>;
}

const td = { padding: "12px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" } as const;
const mono = { ...td, fontFamily: "var(--mono)", color: "var(--text-muted)" } as const;
const selectStyle = {
  padding: "8px 12px", background: "var(--surface-2)", border: "1px solid var(--border)",
  color: "var(--text)", borderRadius: "var(--radius-sm)", fontSize: 13, minWidth: 160,
} as const;

export function Sessions() {
  const [projName, setProjName] = useState("");
  const [projId,   setProjId]   = useState("");
  const [userId,   setUserId]   = useState("");

  const { data: opts } = useApi<FilterOptions>("/filter-options", []);

  const queryParts = [
    projName ? `project_name=${encodeURIComponent(projName)}` : "",
    projId   ? `project_id=${encodeURIComponent(projId)}`     : "",
    userId   ? `user_id=${encodeURIComponent(userId)}`        : "",
  ].filter(Boolean).join("&");
  const queryStr = queryParts ? `?${queryParts}` : "";

  const { data, loading, error } = useApi<{ sessions: SessionSummary[]; total: number }>(
    `/sessions${queryStr}`,
    [projName, projId, userId],
  );

  const availableProjIds = projName && opts?.project_ids?.[projName] ? opts.project_ids[projName] : [];
  const availableUserIds = projId  && opts?.user_ids?.[projId]       ? opts.user_ids[projId]       : [];

  function handleProjName(v: string) {
    setProjName(v);
    setProjId("");
    setUserId("");
  }
  function handleProjId(v: string) {
    setProjId(v);
    setUserId("");
  }

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error || !data) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Failed to load sessions"}</div>;

  return (
    <div>
      <PageHead title="Sessions" kicker={`// ${data.total} tracked`} />

      {/* Cascading filters */}
      {opts && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
          {/* Level 1 — project name (app) */}
          <select value={projName} onChange={(e) => handleProjName(e.target.value)} style={selectStyle}>
            <option value="">All apps</option>
            {opts.project_names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>

          {/* Level 2 — project id (filial), only when app selected */}
          {projName && (
            <select value={projId} onChange={(e) => handleProjId(e.target.value)} style={selectStyle}>
              <option value="">All filials</option>
              {availableProjIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          )}

          {/* Level 3 — user id (phone), only when filial selected */}
          {projId && (
            <select value={userId} onChange={(e) => setUserId(e.target.value)} style={selectStyle}>
              <option value="">All users</option>
              {availableUserIds.map((uid) => <option key={uid} value={uid}>{uid}</option>)}
            </select>
          )}

          {(projName || projId || userId) && (
            <button
              onClick={() => { setProjName(""); setProjId(""); setUserId(""); }}
              style={{ padding: "8px 12px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-faint)", borderRadius: "var(--radius-sm)", cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12 }}
            >
              clear
            </button>
          )}
        </div>
      )}

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Session ID", "App", "Filial", "Traces", "Cost", "Tokens", "First Trace", "Last Trace"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "12px 14px", borderBottom: "1px solid var(--border)", fontSize: 12, color: "var(--text-faint)", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.sessions.map((s) => (
              <tr
                key={s.session_id}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "")}
              >
                <td style={td}><code style={{ fontSize: 12 }}>{s.session_id}</code></td>
                <td style={mono}>{s.project_name ?? <span style={{ opacity: 0.4 }}>—</span>}</td>
                <td style={{ ...mono, fontSize: 11 }}>
                  {s.project_id ? <code>{s.project_id}</code> : <span style={{ opacity: 0.4 }}>—</span>}
                </td>
                <td style={mono}>{s.trace_count}</td>
                <td style={{ ...mono, color: "var(--accent)" }}>${s.total_cost_usd.toFixed(4)}</td>
                <td style={mono}>{s.total_tokens.toLocaleString()}</td>
                <td style={mono}>{new Date(s.first_trace_at).toLocaleString()}</td>
                <td style={mono}>{new Date(s.last_trace_at).toLocaleString()}</td>
              </tr>
            ))}
            {data.sessions.length === 0 && (
              <tr>
                <td colSpan={8} style={{ ...td, textAlign: "center", color: "var(--text-faint)", padding: "32px 14px" }}>
                  No sessions match the current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
