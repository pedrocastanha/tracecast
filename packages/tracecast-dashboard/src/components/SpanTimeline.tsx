import { useState } from "react";

interface SpanData {
  span_id: string;
  parent_span_id: string | null;
  type: string;
  name: string;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  input: string | null;
  output: string | null;
  error: string | null;
}

const TYPE_COLOR: Record<string, string> = {
  llm: "#c8f751",
  tool: "#fbbf24",
  agent: "#a78bfa",
};

const TYPE_LABELS: Record<string, string> = { llm: "LLM", tool: "Tool", agent: "Agent" };

function colorFor(type: string) {
  return TYPE_COLOR[type] ?? "#5eead4";
}

function fmtMs(ms: number | null) {
  if (ms == null) return null;
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

/** Try to pretty-print content. Returns {json: true, text} if parseable, else {json: false, text}. */
function parseContent(raw: string): { isJson: boolean; text: string } {
  const trimmed = raw.trim();
  if ((trimmed.startsWith("{") || trimmed.startsWith("[")) && trimmed.length < 50_000) {
    try {
      const parsed = JSON.parse(trimmed);
      return { isJson: true, text: JSON.stringify(parsed, null, 2) };
    } catch {
      // not valid JSON
    }
  }
  return { isJson: false, text: raw };
}

function ContentBlock({ label, raw, accentColor }: { label: string; raw: string; accentColor: string }) {
  const [expanded, setExpanded] = useState(false);
  const { isJson, text } = parseContent(raw);
  const THRESHOLD = 400;
  const needsTrunc = text.length > THRESHOLD;
  const display = expanded || !needsTrunc ? text : text.slice(0, THRESHOLD) + "…";

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: accentColor, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
          {label}
        </span>
        {isJson && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-faint)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}>
            JSON
          </span>
        )}
      </div>
      <pre
        style={{
          background: "rgba(0,0,0,.25)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 12px",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontSize: 11.5,
          lineHeight: 1.6,
          color: "var(--text-muted)",
          maxHeight: expanded ? 480 : undefined,
          overflowY: expanded ? "auto" : undefined,
          margin: 0,
          fontFamily: "var(--mono)",
        }}
      >
        {display}
      </pre>
      {needsTrunc && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{ marginTop: 4, background: "none", border: "none", color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 11, cursor: "pointer", padding: 0 }}
        >
          {expanded ? "show less ↑" : `show more (${(text.length / 1000).toFixed(1)}k chars) ↓`}
        </button>
      )}
    </div>
  );
}

function SpanCard({ span, depth }: { span: SpanData; depth: number }) {
  const [open, setOpen] = useState(false);
  const color = colorFor(span.type);
  const hasContent = !!(span.input || span.output || span.error);
  const latency = fmtMs(span.latency_ms);
  const hasTokens = span.tokens_in > 0 || span.tokens_out > 0;

  return (
    <div style={{ marginLeft: depth * 14, borderLeft: `2px solid ${color}28`, paddingLeft: depth > 0 ? 10 : 0, marginBottom: 4 }}>
      <div
        onClick={() => hasContent && setOpen((v) => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "9px 12px",
          background: open ? "var(--surface-2)" : "var(--surface)",
          border: "1px solid var(--border)",
          borderLeft: `3px solid ${color}`,
          borderRadius: 8,
          cursor: hasContent ? "pointer" : "default",
          transition: "background .1s ease",
        }}
      >
        {/* Type dot */}
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0, boxShadow: `0 0 5px ${color}55` }} />

        {/* Name */}
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {span.name}
        </span>

        {/* Type badge */}
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-faint)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 5px", flexShrink: 0 }}>
          {TYPE_LABELS[span.type] ?? span.type}
        </span>

        {/* Metrics */}
        <div style={{ display: "flex", gap: 12, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-faint)", flexShrink: 0 }}>
          {hasTokens && (
            <span style={{ color: "var(--accent)" }}>
              {(span.tokens_in + span.tokens_out).toLocaleString()} tok
            </span>
          )}
          {span.cost_usd > 0 && <span>${span.cost_usd.toFixed(4)}</span>}
          {latency && <span>{latency}</span>}
          {span.error && <span style={{ color: "#fb7185" }}>error</span>}
        </div>

        {/* Chevron */}
        {hasContent && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-faint)", transition: "transform .15s", transform: open ? "rotate(90deg)" : "rotate(0deg)", flexShrink: 0 }}>
            ▶
          </span>
        )}
      </div>

      {/* Expanded body */}
      {open && hasContent && (
        <div style={{ padding: "8px 12px 12px 12px", background: "var(--bg-2)", border: "1px solid var(--border)", borderTop: "none", borderRadius: "0 0 8px 8px", marginTop: -4 }}>
          {span.error && (
            <div style={{ padding: "8px 12px", background: "rgba(251,113,133,.08)", border: "1px solid rgba(251,113,133,.25)", borderRadius: 6, color: "#fb7185", fontFamily: "var(--mono)", fontSize: 12, marginTop: 8 }}>
              {span.error}
            </div>
          )}
          {span.input  && <ContentBlock label="Input"  raw={span.input}  accentColor="var(--accent)" />}
          {span.output && <ContentBlock label="Output" raw={span.output} accentColor="#5eead4" />}
        </div>
      )}
    </div>
  );
}

/** Build a depth map keyed by span_id based on parent_span_id */
function buildDepthMap(spans: SpanData[]): Map<string, number> {
  const idSet = new Set(spans.map((s) => s.span_id));
  const depth = new Map<string, number>();
  function getDepth(id: string, visited = new Set<string>()): number {
    if (depth.has(id)) return depth.get(id)!;
    if (visited.has(id)) return 0;
    visited.add(id);
    const span = spans.find((s) => s.span_id === id);
    if (!span?.parent_span_id || !idSet.has(span.parent_span_id)) {
      depth.set(id, 0);
      return 0;
    }
    const d = 1 + getDepth(span.parent_span_id, visited);
    depth.set(id, d);
    return d;
  }
  spans.forEach((s) => getDepth(s.span_id));
  return depth;
}

const TYPE_ORDER = ["llm", "agent", "tool"];

export function SpanTimeline({ spans }: { spans: SpanData[] }) {
  const [filter, setFilter] = useState<string>("all");
  const depthMap = buildDepthMap(spans);

  const types = [...new Set(spans.map((s) => s.type))].sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b));

  const visible = filter === "all" ? spans : spans.filter((s) => s.type === filter);

  return (
    <div>
      {/* Type filter pills */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {["all", ...types].map((t) => {
          const active = filter === t;
          const c = TYPE_COLOR[t] ?? "var(--accent)";
          return (
            <button
              key={t}
              onClick={() => setFilter(t)}
              style={{
                padding: "4px 12px", borderRadius: 20, cursor: "pointer",
                border: `1px solid ${active ? c : "var(--border)"}`,
                background: active ? `${c}18` : "transparent",
                color: active ? c : "var(--text-faint)",
                fontFamily: "var(--mono)", fontSize: 11,
                transition: "all .1s ease",
              }}
            >
              {t === "all" ? `all (${spans.length})` : `${TYPE_LABELS[t] ?? t} (${spans.filter((s) => s.type === t).length})`}
            </button>
          );
        })}
      </div>

      {/* Span cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {visible.map((s) => (
          <SpanCard key={s.span_id} span={s} depth={Math.min(depthMap.get(s.span_id) ?? 0, 4)} />
        ))}
      </div>
    </div>
  );
}
