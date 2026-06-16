import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

function ScoreBar({ score }: { score: number }) {
  const color = score >= 0.7 ? "var(--green)" : score >= 0.4 ? "var(--yellow)" : "var(--red)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 60, height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", display: "inline-block" }}>
        <span style={{ width: `${Math.round(score * 100)}%`, height: 6, background: color, display: "block" }} />
      </span>
      {score.toFixed(2)}
    </span>
  );
}

function Turn({ turn }: { turn: AnyObj }) {
  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }}>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>turn #{turn.index} · {turn.passed ? "pass" : "fail"} · {turn.overall_score?.toFixed(2)}</div>
      {turn.input && <div style={{ fontSize: 12, marginTop: 4 }}><strong>Input:</strong> {turn.input}</div>}
      <div style={{ fontSize: 12, marginTop: 4 }}><strong style={{ color: "var(--accent)" }}>Output:</strong>
        <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{turn.output}</pre>
      </div>
      {turn.expected && <div style={{ fontSize: 12 }}><strong>Expected:</strong> {turn.expected}</div>}
      {turn.scores?.length > 0 && (
        <table style={{ width: "100%", marginTop: 8, fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
              <th style={{ padding: 4 }}>Criterion</th><th style={{ padding: 4 }}>Kind</th>
              <th style={{ padding: 4 }}>Score</th><th style={{ padding: 4 }}>Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {turn.scores.map((s: AnyObj, i: number) => (
              <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: 4 }}>{s.name}</td>
                <td style={{ padding: 4, color: "var(--text-muted)" }}>{s.kind}</td>
                <td style={{ padding: 4 }}><ScoreBar score={s.score} /></td>
                <td style={{ padding: 4, color: "var(--text-muted)" }}>{s.reasoning ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Case({ c, navigate }: { c: AnyObj; navigate: (p: string) => void }) {
  const [open, setOpen] = useState(false);
  const color = c.status === "error" ? "var(--red)" : c.passed ? "var(--green)" : "var(--yellow)";
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, marginBottom: 8 }}>
      <div onClick={() => setOpen(!open)}
        style={{ padding: 12, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span><strong>{c.case_id}</strong> <span style={{ color, marginLeft: 8 }}>{c.status}</span></span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>score {c.overall_score?.toFixed(2)} {open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {c.error && <pre style={{ color: "var(--red)", fontSize: 12 }}>{c.error}</pre>}
          {c.turns?.map((t: AnyObj) => <Turn key={t.index} turn={t} />)}
          {c.trace_id && (
            <button onClick={() => navigate(`/traces/${c.trace_id}`)}
              style={{ marginTop: 8, padding: "4px 10px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>
              ver trace →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function EvalRunDetail() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { data: run, loading, error } = useApi<AnyObj>(`/evals/${runId}`, [runId]);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error || !run) return <div style={{ color: "var(--red)" }}>Error: {error ?? "Run not found"}</div>;

  return (
    <div>
      <button onClick={() => navigate(-1)}
        style={{ marginBottom: 16, padding: "6px 14px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer" }}>
        &larr; Back
      </button>
      <h2 style={{ fontSize: 18, fontWeight: 600 }}>{run.name}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
        Dataset: {run.dataset_name ?? "—"} | Judge: {run.judge_model ?? "—"} | Threshold: {run.threshold}
      </p>
      <p style={{ fontSize: 13, marginTop: 4 }}>
        Pass rate: <strong>{run.pass_rate != null ? `${(run.pass_rate * 100).toFixed(0)}%` : "—"}</strong> ({run.passed}/{run.total_cases}) ·
        Avg score: {run.avg_score?.toFixed(3)} · Judge cost: ${run.judge_cost_usd?.toFixed(4)}
      </p>
      <h3 style={{ marginTop: 16, fontSize: 14 }}>Cases ({run.cases?.length ?? 0})</h3>
      {run.cases?.map((c: AnyObj) => <Case key={c.case_id} c={c} navigate={navigate} />)}
    </div>
  );
}
