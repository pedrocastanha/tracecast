interface SpanData {
  span_id: string;
  type: string;
  name: string;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number | null;
  input: string | null;
  output: string | null;
}

export function SpanTimeline({ spans }: { spans: SpanData[] }) {
  const borderColors: Record<string, string> = { llm: "var(--accent)", tool: "var(--yellow)", agent: "var(--green)" };
  return (
    <div>
      {spans.map((s) => (
        <div key={s.span_id} style={{ padding: 12, margin: "8px 0", background: "var(--bg)", borderRadius: 6, borderLeft: `3px solid ${borderColors[s.type] ?? "var(--accent)"}` }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {s.name} <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{s.type}</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 16, flexWrap: "wrap" }}>
            {s.model && <span>Model: {s.model}</span>}
            <span>Tokens: {s.tokens_in.toLocaleString()} in / {s.tokens_out.toLocaleString()} out</span>
            <span>Cost: ${s.cost_usd.toFixed(4)}</span>
            <span>Latency: {s.latency_ms != null ? (s.latency_ms < 1000 ? `${s.latency_ms}ms` : `${(s.latency_ms / 1000).toFixed(2)}s`) : "—"}</span>
          </div>
          {s.input && (
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <strong style={{ color: "var(--accent)" }}>Input:</strong>
              <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "var(--text)", maxHeight: 150, overflowY: "auto" }}>
                {s.input.length > 500 ? s.input.slice(0, 500) + "..." : s.input}
              </pre>
            </div>
          )}
          {s.output && (
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <strong style={{ color: "var(--accent)" }}>Output:</strong>
              <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "var(--text)", maxHeight: 150, overflowY: "auto" }}>
                {s.output.length > 500 ? s.output.slice(0, 500) + "..." : s.output}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
