import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { SpanTimeline } from "../components/SpanTimeline";
import { TraceGraph } from "../components/TraceGraph";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

export function TraceDetail() {
  const { traceId } = useParams();
  const navigate = useNavigate();
  const { data: t, loading, error } = useApi<AnyObj>(`/traces/${traceId}`, [traceId]);
  const { data: graph } = useApi<AnyObj>(`/traces/${traceId}/graph`, [traceId]);
  const [tab, setTab] = useState<"graph" | "list">("graph");
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error || !t) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Trace not found"}</div>;

  const selectedSpan = t.spans?.find((s: AnyObj) => s.span_id === selected) ?? null;

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
              {selectedSpan.input && (
                <div style={{ marginTop: 8, fontSize: 12 }}>
                  <strong style={{ color: "var(--accent)" }}>Input:</strong>
                  <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 200, overflowY: "auto" }}>{selectedSpan.input}</pre>
                </div>
              )}
              {selectedSpan.output && (
                <div style={{ marginTop: 8, fontSize: 12 }}>
                  <strong style={{ color: "var(--accent)" }}>Output:</strong>
                  <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 200, overflowY: "auto" }}>{selectedSpan.output}</pre>
                </div>
              )}
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
    </div>
  );
}
