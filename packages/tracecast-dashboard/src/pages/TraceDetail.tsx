import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { SpanTimeline } from "../components/SpanTimeline";
import { TraceGraph } from "../components/TraceGraph";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

const IO_TRUNCATE = 600;

function SpanIODisplay({ label, content }: { label: string; content: string }) {
  const [expanded, setExpanded] = useState(false);

  // Try to format as JSON for readability
  let display = content;
  try {
    const parsed = JSON.parse(content);
    display = JSON.stringify(parsed, null, 2);
  } catch {
    // keep as-is (Python repr, plain string, etc.)
  }

  const needsTrunc = display.length > IO_TRUNCATE;
  const shown = expanded || !needsTrunc ? display : display.slice(0, IO_TRUNCATE) + "…";

  return (
    <div style={{ marginTop: 8, fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <strong style={{ color: "var(--accent)" }}>{label}:</strong>
        {needsTrunc && (
          <button
            onClick={() => setExpanded((v) => !v)}
            style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              border: "1px solid var(--border)", background: "var(--surface-2)",
              color: "var(--text-muted)", cursor: "pointer",
            }}
          >
            {expanded ? "show less" : `show raw (${display.length} chars)`}
          </button>
        )}
      </div>
      <pre style={{
        background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
        padding: 8, whiteSpace: "pre-wrap", wordBreak: "break-word",
        maxHeight: expanded ? 400 : 180, overflowY: "auto",
      }}>
        {shown}
      </pre>
    </div>
  );
}

export function TraceDetail() {
  const { traceId } = useParams();
  const navigate = useNavigate();
  const { data: t, loading, error } = useApi<AnyObj>(`/traces/${traceId}`, [traceId]);
  const { data: graph } = useApi<AnyObj>(`/traces/${traceId}/graph`, [traceId]);
  const { data: scoresData } = useApi<AnyObj>(`/traces/${traceId}/scores`, [traceId]);
  const [tab, setTab] = useState<"graph" | "list">("graph");
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error || !t) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Trace not found"}</div>;

  const selectedSpan = t.spans?.find((s: AnyObj) => s.span_id === selected) ?? null;
  const scores = scoresData?.scores ?? [];

  const kindColor = (k: string) =>
    k === "human" ? "var(--accent)" : k === "llm" ? "var(--yellow)" : "var(--green)";

  const tabBtn = (key: "graph" | "list", label: string) => {
    const active = tab === key;
    return (
      <button
        onClick={() => setTab(key)}
        style={{
          padding: "7px 16px",
          border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
          background: active ? "var(--accent-dim)" : "var(--surface-2)",
          color: active ? "var(--accent)" : "var(--text-muted)",
          fontWeight: active ? 600 : 500,
          borderRadius: "var(--radius-sm)",
          cursor: "pointer",
          marginRight: 8,
        }}
      >
        {label}
      </button>
    );
  };

  return (
    <div>
      <button onClick={() => navigate(-1)}
        style={{ marginBottom: 18, padding: "7px 14px", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-muted)", borderRadius: "var(--radius-sm)", cursor: "pointer" }}>
        &larr; Back
      </button>
      <h2 style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.025em" }}>{t.name}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
        Trace ID: <code>{t.trace_id}</code>
      </p>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
        Model: {t.model ?? "—"} | Cost: ${t.cost_usd?.toFixed(4)} | Latency: {t.latency_ms != null ? `${t.latency_ms}ms` : "—"} | Tokens: {t.total_tokens}
      </p>

      <div style={{ margin: "16px 0" }}>
        {tabBtn("graph", "Graph")}
        {tabBtn("list", "List")}
      </div>

      {tab === "graph" && graph && graph.nodes?.length > 0 && (
        <>
          <TraceGraph data={graph} onSelect={setSelected} />
          {selectedSpan && (
            <div style={{ marginTop: 16, padding: 12, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>
                {selectedSpan.name} <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{selectedSpan.type}</span>
                {selectedSpan.status === "error" && <span style={{ color: "var(--red)", marginLeft: 8 }}>error</span>}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 16, flexWrap: "wrap" }}>
                {selectedSpan.model && <span>Model: {selectedSpan.model}</span>}
                <span>Tokens: {selectedSpan.tokens_in} in / {selectedSpan.tokens_out} out</span>
                <span>Cost: ${selectedSpan.cost_usd?.toFixed(4)}</span>
                <span>Latency: {selectedSpan.latency_ms != null ? `${selectedSpan.latency_ms}ms` : "—"}</span>
              </div>
              {selectedSpan.error && <pre style={{ color: "var(--red)", fontSize: 12, marginTop: 8 }}>{selectedSpan.error}</pre>}
              {selectedSpan.input && <SpanIODisplay label="Input" content={selectedSpan.input} />}
              {selectedSpan.output && <SpanIODisplay label="Output" content={selectedSpan.output} />}
            </div>
          )}
        </>
      )}

      {tab === "list" && t.spans?.length > 0 && (
        <>
          <h3 style={{ marginTop: 16, fontSize: 14 }}>Spans ({t.spans.length})</h3>
          <SpanTimeline spans={t.spans} />
        </>
      )}

      <div style={{ marginTop: 28 }}>
        <h3 style={{ fontSize: 14, marginBottom: 10 }}>Scores ({scores.length})</h3>
        {scores.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            No scores attached. Use <code>tracecast.score(trace_id, ...)</code> or enable online eval.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: 8 }}>Name</th>
                <th style={{ padding: 8 }}>Value</th>
                <th style={{ padding: 8 }}>Kind</th>
                <th style={{ padding: 8 }}>Source</th>
                <th style={{ padding: 8 }}>Comment</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s: AnyObj) => (
                <tr key={s.score_id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 8 }}>{s.name}</td>
                  <td style={{ padding: 8, fontFamily: "var(--mono)" }}>
                    {s.string_value ?? (typeof s.value === "number" ? s.value : String(s.value))}
                  </td>
                  <td style={{ padding: 8, color: kindColor(s.kind), fontWeight: 600 }}>{s.kind}</td>
                  <td style={{ padding: 8, color: "var(--text-muted)" }}>{s.source ?? "—"}</td>
                  <td style={{ padding: 8, color: "var(--text-muted)" }}>{s.comment ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
