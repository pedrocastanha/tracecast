import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { SpanTimeline } from "../components/SpanTimeline";
import { TraceGraph } from "../components/TraceGraph";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

const IO_TRUNCATE = 600;

function fmtMs(ms: number | null | undefined) {
  if (ms == null) return "—";
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

function StatChip({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 3,
      padding: "8px 14px",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderTop: `2px solid ${accent ?? "var(--border-strong)"}`,
      borderRadius: "var(--radius-sm)",
      minWidth: 90,
    }}>
      <span style={{ fontSize: 9.5, fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-faint)", fontWeight: 600 }}>
        {label}
      </span>
      <span style={{ fontSize: 13.5, fontFamily: "var(--mono)", fontWeight: 600, color: accent ?? "var(--text)", whiteSpace: "nowrap" }}>
        {value}
      </span>
    </div>
  );
}

function SpanIODisplay({ label, content, accentColor }: { label: string; content: string; accentColor?: string }) {
  const [expanded, setExpanded] = useState(false);

  let display = content;
  try {
    const parsed = JSON.parse(content);
    display = JSON.stringify(parsed, null, 2);
  } catch {
    // keep as-is
  }

  const needsTrunc = display.length > IO_TRUNCATE;
  const shown = expanded || !needsTrunc ? display : display.slice(0, IO_TRUNCATE) + "…";
  const ac = accentColor ?? "var(--accent)";

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
        <span style={{ fontSize: 9.5, fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.08em", color: ac, fontWeight: 700 }}>
          {label}
        </span>
        {needsTrunc && (
          <button onClick={() => setExpanded((v) => !v)} style={{
            fontSize: 10, padding: "2px 8px", borderRadius: 4,
            border: "1px solid var(--border)", background: "var(--surface-2)",
            color: "var(--text-muted)", cursor: "pointer",
          }}>
            {expanded ? "collapse ↑" : `+${Math.round((display.length - IO_TRUNCATE) / 1000)}k chars ↓`}
          </button>
        )}
      </div>
      <pre style={{
        background: "rgba(0,0,0,.3)", border: "1px solid var(--border)", borderLeft: `2px solid ${ac}44`,
        borderRadius: 6, padding: "10px 12px", whiteSpace: "pre-wrap", wordBreak: "break-word",
        maxHeight: expanded ? 480 : 180, overflowY: "auto", margin: 0,
        fontFamily: "var(--mono)", fontSize: 11.5, lineHeight: 1.65, color: "var(--text-muted)",
      }}>
        {shown}
      </pre>
    </div>
  );
}

function LlmCallBlock({ call, index }: { call: AnyObj; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 7, marginBottom: 6, overflow: "hidden" }}>
      <div
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex", gap: 12, alignItems: "center", padding: "8px 12px",
          cursor: "pointer", background: open ? "var(--surface-2)" : "var(--surface)",
          transition: "background .1s",
        }}
      >
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-faint)", minWidth: 18 }}>
          #{index + 1}
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--accent)", flex: 1 }}>
          {call.model ?? "—"}
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-muted)" }}>
          {(call.tokens_in + call.tokens_out).toLocaleString()} tok
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--text-faint)" }}>
          {call.tokens_in}↑ {call.tokens_out}↓
        </span>
        {call.cost_usd > 0 && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--yellow)" }}>
            ${call.cost_usd.toFixed(4)}
          </span>
        )}
        <span style={{ color: "var(--text-faint)", fontSize: 10, transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▶</span>
      </div>
      {open && (
        <div style={{ padding: "4px 12px 12px 12px", background: "var(--bg-2)" }}>
          {call.input  && <SpanIODisplay label="Prompt"     content={call.input}  accentColor="var(--accent)" />}
          {call.output && <SpanIODisplay label="Completion" content={call.output} accentColor="var(--cyan)" />}
        </div>
      )}
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

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-faint)", paddingTop: 40 }}>
      <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid var(--accent)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      Loading trace…
    </div>
  );
  if (error || !t) return <div style={{ color: "var(--red)", paddingTop: 40 }}>Trace not found: {error}</div>;

  const selectedSpan = t.spans?.find((s: AnyObj) => s.span_id === selected) ?? null;
  const selectedNode = graph?.nodes?.find((n: AnyObj) => n.id === selected) ?? null;
  const scores = scoresData?.scores ?? [];

  return (
    <div className="page-enter">
      {/* Back */}
      <button onClick={() => navigate(-1)} style={{
        display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 22,
        padding: "6px 12px", border: "1px solid var(--border)", background: "transparent",
        color: "var(--text-muted)", borderRadius: "var(--radius-sm)", cursor: "pointer", fontSize: 12,
      }}>
        ← Back
      </button>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 6 }}>
          {t.name}
        </h2>
        <code style={{ fontSize: 11, color: "var(--text-faint)" }}>{t.trace_id}</code>
      </div>

      {(t.is_summary || t.export_status === "summary_only") && (
        <div style={{
          marginBottom: 20, padding: "12px 16px",
          border: "1px solid rgba(251,191,36,.4)", borderLeft: "3px solid var(--yellow)",
          background: "rgba(251,191,36,.08)", borderRadius: "var(--radius-sm)",
          color: "var(--text)", fontSize: 13, lineHeight: 1.5,
        }}>
          <strong style={{ color: "var(--yellow)" }}>Partial export</strong>
          {" — full spans/payload were not saved. Showing date, tokens, project and type only."}
          {t.export_error && (
            <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-muted)" }}>
              {t.export_error}
            </div>
          )}
        </div>
      )}

      {/* Stat chips */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
        {t.model && <StatChip label="Model"   value={t.model}                     accent="var(--violet)" />}
        <StatChip label="Cost"    value={`$${t.cost_usd?.toFixed(4) ?? "0"}`}    accent="var(--yellow)" />
        <StatChip label="Latency" value={fmtMs(t.latency_ms)}                    accent="var(--cyan)" />
        <StatChip label="Tokens"  value={(t.total_tokens ?? 0).toLocaleString()}  accent="var(--accent)" />
        {t.total_tokens_in_cached > 0 && (
          <StatChip label="Cached" value={(t.total_tokens_in_cached ?? 0).toLocaleString()} accent="var(--green)" />
        )}
        {(t.project_id || t.project_name) && (
          <StatChip label="Project" value={t.project_name || t.project_id} accent="var(--violet)" />
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 20, borderBottom: "1px solid var(--border)", paddingBottom: 0 }}>
        {(["graph", "list"] as const).map((key) => {
          const active = tab === key;
          return (
            <button key={key} onClick={() => setTab(key)} style={{
              padding: "8px 20px", border: "none", borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
              background: "transparent", color: active ? "var(--accent)" : "var(--text-muted)",
              fontFamily: "var(--ui)", fontSize: 13, fontWeight: active ? 600 : 400,
              cursor: "pointer", marginBottom: -1, transition: "all .15s ease",
            }}>
              {key === "graph" ? "Graph" : "List"}
            </button>
          );
        })}
      </div>

      {/* Graph tab */}
      {tab === "graph" && graph && graph.nodes?.length > 0 && (
        <>
          <TraceGraph data={graph} onSelect={setSelected} />

          {(selectedSpan || selectedNode) && (
            <div style={{
              marginTop: 16, padding: "16px 20px",
              border: "1px solid var(--border-strong)", borderRadius: "var(--radius)",
              background: "var(--surface)", borderLeft: "3px solid var(--accent)",
            }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 15, fontWeight: 700, fontFamily: "var(--mono)" }}>
                  {selectedSpan?.name ?? selectedNode?.name}
                </span>
                <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-faint)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 5px" }}>
                  {selectedSpan?.type}
                </span>
              </div>
              {selectedSpan && (
                <div style={{ display: "flex", gap: 18, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--text-muted)", flexWrap: "wrap", marginBottom: 12 }}>
                  {selectedSpan.model && <span style={{ color: "var(--violet)" }}>{selectedSpan.model}</span>}
                  <span>{selectedSpan.tokens_in?.toLocaleString()} in / {selectedSpan.tokens_out?.toLocaleString()} out</span>
                  {selectedSpan.cost_usd > 0 && <span style={{ color: "var(--yellow)" }}>${selectedSpan.cost_usd?.toFixed(4)}</span>}
                  {selectedSpan.latency_ms != null && <span style={{ color: "var(--cyan)" }}>{fmtMs(selectedSpan.latency_ms)}</span>}
                </div>
              )}
              {selectedSpan?.error && (
                <div style={{ padding: "8px 12px", background: "rgba(251,113,133,.08)", border: "1px solid rgba(251,113,133,.2)", borderRadius: 6, color: "var(--red)", fontFamily: "var(--mono)", fontSize: 12, marginBottom: 10 }}>
                  {selectedSpan.error}
                </div>
              )}
              {selectedNode?.tool_params && (
                <SpanIODisplay label="Params" content={JSON.stringify(selectedNode.tool_params, null, 2)} accentColor="var(--yellow)" />
              )}
              {selectedSpan?.input  && <SpanIODisplay label="Input"  content={selectedSpan.input}  accentColor="var(--accent)" />}
              {selectedSpan?.output && <SpanIODisplay label="Output" content={selectedSpan.output} accentColor="var(--cyan)" />}
              {selectedNode?.llm_calls?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 10, fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent)", fontWeight: 700, marginBottom: 8 }}>
                    LLM Calls ({selectedNode.llm_calls.length})
                  </div>
                  {selectedNode.llm_calls.map((c: AnyObj, i: number) => (
                    <LlmCallBlock key={i} call={c} index={i} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* List tab */}
      {tab === "list" && t.spans?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-faint)", marginBottom: 14, letterSpacing: "0.05em", textTransform: "uppercase" }}>
            {t.spans.length} spans
          </div>
          <SpanTimeline spans={t.spans} />
        </div>
      )}

      {/* Scores */}
      <div style={{ marginTop: 32, paddingTop: 24, borderTop: "1px solid var(--border)" }}>
        <div style={{ fontSize: 10, fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-faint)", fontWeight: 600, marginBottom: 14 }}>
          Scores ({scores.length})
        </div>
        {scores.length === 0 ? (
          <p style={{ color: "var(--text-faint)", fontSize: 12, fontFamily: "var(--mono)" }}>
            No scores attached.{" "}
            <code style={{ color: "var(--accent)", background: "var(--accent-dim)", padding: "1px 6px", borderRadius: 4 }}>
              tracecast.score(trace_id, ...)
            </code>
          </p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Name", "Value", "Kind", "Source", "Comment"].map((h) => (
                  <th key={h} style={{ padding: "6px 10px", textAlign: "left" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scores.map((s: AnyObj) => (
                <tr key={s.score_id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "8px 10px", fontFamily: "var(--mono)" }}>{s.name}</td>
                  <td style={{ padding: "8px 10px", fontFamily: "var(--mono)", color: "var(--accent)" }}>
                    {s.string_value ?? (typeof s.value === "number" ? s.value : String(s.value))}
                  </td>
                  <td style={{ padding: "8px 10px", color: s.kind === "human" ? "var(--accent)" : s.kind === "llm" ? "var(--yellow)" : "var(--green)", fontWeight: 600 }}>
                    {s.kind}
                  </td>
                  <td style={{ padding: "8px 10px", color: "var(--text-muted)" }}>{s.source ?? "—"}</td>
                  <td style={{ padding: "8px 10px", color: "var(--text-muted)" }}>{s.comment ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
