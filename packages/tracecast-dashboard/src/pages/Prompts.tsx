import { useState } from "react";
import { useApi, fetchApi } from "../hooks/useApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

function LabelChip({ label }: { label: string }) {
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: 11, padding: "2px 8px", borderRadius: 4,
      background: "var(--accent-dim)", color: "var(--accent)", marginRight: 6,
    }}>
      {label}
    </span>
  );
}

function PromptRow({ p }: { p: AnyObj }) {
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState<AnyObj[] | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && versions === null) {
      try {
        const detail = await fetchApi<AnyObj>(`/prompts/${encodeURIComponent(p.name)}`);
        setVersions(detail.versions ?? []);
      } catch {
        setVersions([]);
      }
    }
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, marginBottom: 8 }}>
      <div onClick={toggle}
        style={{ padding: 12, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>
          <strong style={{ fontFamily: "var(--mono)" }}>{p.name}</strong>
          <span style={{ marginLeft: 12 }}>{p.labels?.map((l: string) => <LabelChip key={l} label={l} />)}</span>
        </span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          v{p.latest_version} · {p.versions} version{p.versions === 1 ? "" : "s"} {open ? "▲" : "▼"}
        </span>
      </div>
      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {versions === null && <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Loading…</div>}
          {versions?.map((v: AnyObj) => (
            <div key={v.version} style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                version {v.version}
                {v.labels?.length > 0 && <span style={{ marginLeft: 10 }}>{v.labels.map((l: string) => <LabelChip key={l} label={l} />)}</span>}
              </div>
              <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 6, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12 }}>{v.template}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Prompts() {
  const { data, loading, error } = useApi<AnyObj>("/prompts", []);
  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading…</div>;
  if (error) return <div style={{ color: "var(--red)" }}>Error: {error}</div>;

  const prompts = data?.prompts ?? [];
  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Prompts</h2>
      {prompts.length === 0 ? (
        <div style={{ color: "var(--text-muted)" }}>
          No prompts yet. Create one with <code>tracecast.create_prompt(name, template, labels=[...])</code>.
        </div>
      ) : (
        prompts.map((p: AnyObj) => <PromptRow key={p.name} p={p} />)
      )}
    </div>
  );
}
