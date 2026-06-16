import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { PageHead } from "./Overview";

interface TraceSummary {
  trace_id: string;
  name: string;
  started_at: string;
  latency_ms: number | null;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_usd: number;
  span_count: number;
  model: string | null;
}

const inputStyle = { padding: "8px 12px", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: "var(--radius-sm)", fontSize: 13 } as const;
const td = { padding: "12px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" } as const;
const mono = { ...td, fontFamily: "var(--mono)", color: "var(--text-muted)" } as const;

function pageBtn(disabled: boolean) {
  return { padding: "7px 14px", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", borderRadius: "var(--radius-sm)", cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.3 : 1 } as const;
}

export function Traces() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("date");
  const [order, setOrder] = useState("desc");
  const [projectId, setProjectId] = useState("");
  const [userId, setUserId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const params = `?page=${page}&page_size=50&sort_by=${sortBy}&order=${order}` +
    (projectId ? `&project_id=${encodeURIComponent(projectId)}` : "") +
    (userId ? `&user_id=${encodeURIComponent(userId)}` : "") +
    (fromDate ? `&from=${encodeURIComponent(fromDate + "T00:00:00")}` : "") +
    (toDate   ? `&to=${encodeURIComponent(toDate + "T23:59:59")}` : "");

  const { data, loading } = useApi<{ traces: TraceSummary[]; total: number; page: number }>(`/traces${params}`, [page, sortBy, order, projectId, userId, fromDate, toDate]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setOrder(order === "desc" ? "asc" : "desc");
    else { setSortBy(col); setOrder("desc"); }
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / 50) : 0;

  return (
    <div>
      <PageHead title="Traces" kicker={data ? `// ${data.total} captured` : "// loading"} />

      <div style={{ display: "flex", gap: 8, marginBottom: 18, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="Project ID" value={projectId} onChange={(e) => { setProjectId(e.target.value); setPage(1); }} style={inputStyle} />
        <input placeholder="User ID" value={userId} onChange={(e) => { setUserId(e.target.value); setPage(1); }} style={inputStyle} />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-faint)" }}>from</span>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
            style={inputStyle}
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-faint)" }}>to</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => { setToDate(e.target.value); setPage(1); }}
            style={inputStyle}
          />
        </div>
        {(fromDate || toDate) && (
          <button
            onClick={() => { setFromDate(""); setToDate(""); setPage(1); }}
            style={{ padding: "8px 12px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-faint)", borderRadius: "var(--radius-sm)", cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12 }}
          >
            clear dates
          </button>
        )}
      </div>

      {loading ? <div style={{ color: "var(--text-muted)" }}>Loading…</div> : (
        <>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {[{ key: "name", label: "Name" }, { key: "date", label: "Date" }, { key: "duration", label: "Latency" }, { key: "tokens", label: "Tokens" }, { key: "cost", label: "Cost" }, { key: "", label: "Spans" }].map((col) => (
                      <th key={col.label} onClick={() => col.key && toggleSort(col.key)}
                        style={{ textAlign: "left", padding: "12px 14px", borderBottom: "1px solid var(--border)", cursor: col.key ? "pointer" : "default", color: sortBy === col.key ? "var(--accent)" : undefined }}>
                        {col.label} {sortBy === col.key ? (order === "desc" ? "↓" : "↑") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data?.traces ?? []).map((t) => (
                    <tr key={t.trace_id} onClick={() => navigate(`/traces/${t.trace_id}`)}
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
                      <td style={{ ...td, fontWeight: 500 }}>{t.name}</td>
                      <td style={mono}>{new Date(t.started_at).toLocaleString()}</td>
                      <td style={mono}>{t.latency_ms != null ? (t.latency_ms < 1000 ? `${t.latency_ms}ms` : `${(t.latency_ms / 1000).toFixed(2)}s`) : "—"}</td>
                      <td style={mono}>{t.total_tokens_in.toLocaleString()} / {t.total_tokens_out.toLocaleString()}</td>
                      <td style={{ ...mono, color: "var(--accent)" }}>${t.cost_usd.toFixed(4)}</td>
                      <td style={mono}>{t.span_count}</td>
                    </tr>
                  ))}
                  {(data?.traces ?? []).length === 0 && (
                    <tr><td colSpan={6} style={{ ...td, textAlign: "center", color: "var(--text-faint)", padding: "32px 14px" }}>No traces yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 18, justifyContent: "center", alignItems: "center" }}>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={pageBtn(page <= 1)}>Prev</button>
            <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: 13 }}>{page} / {totalPages || 1}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={pageBtn(page >= totalPages)}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
