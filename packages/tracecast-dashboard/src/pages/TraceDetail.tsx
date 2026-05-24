import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { SpanTimeline } from "../components/SpanTimeline";

export function TraceDetail() {
  const { traceId } = useParams();
  const navigate = useNavigate();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: t, loading } = useApi<any>(`/traces/${traceId}`, [traceId]);

  if (loading || !t) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div>
      <button onClick={() => navigate(-1)}
        style={{ marginBottom: 16, padding: "6px 14px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer" }}>
        &larr; Back
      </button>
      <h2 style={{ fontSize: 18, fontWeight: 600 }}>{t.name}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
        Trace ID: <code>{t.trace_id}</code>
      </p>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
        Model: {t.model ?? "—"} | Cost: ${t.cost_usd?.toFixed(4)} | Latency: {t.latency_ms != null ? `${t.latency_ms}ms` : "—"}
      </p>
      {t.spans?.length > 0 && (
        <>
          <h3 style={{ marginTop: 16, fontSize: 14 }}>Spans ({t.spans.length})</h3>
          <SpanTimeline spans={t.spans} />
        </>
      )}
    </div>
  );
}
