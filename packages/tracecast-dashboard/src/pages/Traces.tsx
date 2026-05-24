import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";

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

export function Traces() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("date");
  const [order, setOrder] = useState("desc");
  const [projectId, setProjectId] = useState("");
  const [userId, setUserId] = useState("");

  const params = `?page=${page}&page_size=50&sort_by=${sortBy}&order=${order}` +
    (projectId ? `&project_id=${encodeURIComponent(projectId)}` : "") +
    (userId ? `&user_id=${encodeURIComponent(userId)}` : "");

  const { data, loading } = useApi<{ traces: TraceSummary[]; total: number; page: number }>(`/traces${params}`, [page, sortBy, order, projectId, userId]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setOrder(order === "desc" ? "asc" : "desc");
    else { setSortBy(col); setOrder("desc"); }
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / 50) : 0;

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Traces</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="Project ID" value={projectId} onChange={(e) => { setProjectId(e.target.value); setPage(1); }}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }} />
        <input placeholder="User ID" value={userId} onChange={(e) => { setUserId(e.target.value); setPage(1); }}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }} />
        {data && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{data.total} traces</span>}
      </div>
      {loading ? <div style={{ color: "var(--text-muted)" }}>Loading...</div> : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {[{ key: "name", label: "Name" }, { key: "date", label: "Date" }, { key: "duration", label: "Latency" }, { key: "tokens", label: "Tokens" }, { key: "cost", label: "Cost" }, { key: "", label: "Spans" }].map((col) => (
                    <th key={col.label} onClick={() => col.key && toggleSort(col.key)}
                      style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontWeight: 600, cursor: col.key ? "pointer" : "default" }}>
                      {col.label} {sortBy === col.key ? (order === "desc" ? "↓" : "↑") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.traces ?? []).map((t) => (
                  <tr key={t.trace_id} onClick={() => navigate(`/traces/${t.trace_id}`)}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.name}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(t.started_at).toLocaleString()}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.latency_ms != null ? (t.latency_ms < 1000 ? `${t.latency_ms}ms` : `${(t.latency_ms / 1000).toFixed(2)}s`) : "—"}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.total_tokens_in.toLocaleString()} / {t.total_tokens_out.toLocaleString()}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${t.cost_usd.toFixed(4)}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.span_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "center", alignItems: "center" }}>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}
              style={{ padding: "6px 12px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer", opacity: page <= 1 ? 0.3 : 1 }}>Prev</button>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}
              style={{ padding: "6px 12px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer", opacity: page >= totalPages ? 0.3 : 1 }}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
