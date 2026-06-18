import { useEffect, useState } from "react";
import { useApi, fetchApi } from "../hooks/useApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

function delta(n: number | null | undefined) {
  if (n == null) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(3)}`;
}

function deltaColor(n: number | null | undefined) {
  if (n == null) return "var(--text-muted)";
  if (n < 0) return "var(--red)";
  if (n > 0) return "var(--green)";
  return "var(--text-muted)";
}

const selectStyle = {
  padding: "7px 12px", border: "1px solid var(--border)", background: "var(--surface-2)",
  color: "var(--text)", borderRadius: "var(--radius-sm)", fontSize: 13, minWidth: 260,
} as const;

export function EvalCompare() {
  const { data: list } = useApi<AnyObj>("/evals?limit=200", []);
  const runs: AnyObj[] = list?.evals ?? [];
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [result, setResult] = useState<AnyObj | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!a || !b) { setResult(null); return; }
    setError(null);
    fetchApi<AnyObj>(`/evals/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`)
      .then(setResult)
      .catch((e: Error) => setError(e.message));
  }, [a, b]);

  const label = (r: AnyObj) => `${r.name} · ${r.dataset_name ?? "—"} · ${r.started_at?.slice(0, 19).replace("T", " ")}`;

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Compare runs</h2>

      <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.07em" }}>Run A (baseline)</div>
          <select style={selectStyle} value={a} onChange={(e) => setA(e.target.value)}>
            <option value="">Select run…</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{label(r)}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.07em" }}>Run B (candidate)</div>
          <select style={selectStyle} value={b} onChange={(e) => setB(e.target.value)}>
            <option value="">Select run…</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{label(r)}</option>)}
          </select>
        </div>
      </div>

      {error && <div style={{ color: "var(--red)" }}>Error: {error}</div>}

      {result && (
        <>
          {result.dataset_mismatch && (
            <div style={{ color: "var(--yellow)", fontSize: 13, marginBottom: 12 }}>
              ⚠ Runs use different datasets — cases aligned by id.
            </div>
          )}
          <div style={{ display: "flex", gap: 24, marginBottom: 18, fontSize: 14 }}>
            <span>Avg score Δ: <strong style={{ color: deltaColor(result.avg_score_delta) }}>{delta(result.avg_score_delta)}</strong></span>
            <span>Pass rate Δ: <strong style={{ color: deltaColor(result.pass_rate_delta) }}>{delta(result.pass_rate_delta)}</strong></span>
          </div>

          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: 8 }}>Case</th>
                <th style={{ padding: 8 }}>A</th>
                <th style={{ padding: 8 }}>B</th>
                <th style={{ padding: 8 }}>Δ</th>
                <th style={{ padding: 8 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {result.cases?.map((c: AnyObj) => (
                <tr key={c.case_id}
                  style={{ borderBottom: "1px solid var(--border)", background: c.delta != null && c.delta < 0 ? "rgba(255,90,90,0.06)" : "transparent" }}>
                  <td style={{ padding: 8, fontFamily: "var(--mono)" }}>{c.case_id}</td>
                  <td style={{ padding: 8 }}>{c.score_a != null ? c.score_a.toFixed(3) : "—"}</td>
                  <td style={{ padding: 8 }}>{c.score_b != null ? c.score_b.toFixed(3) : "—"}</td>
                  <td style={{ padding: 8, color: deltaColor(c.delta), fontWeight: 600 }}>{delta(c.delta)}</td>
                  <td style={{ padding: 8, color: "var(--text-muted)" }}>{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
