import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = any;

function pct(v: number | null | undefined) {
  return v != null ? `${(v * 100).toFixed(0)}%` : "—";
}

export function Evaluators() {
  const navigate = useNavigate();
  const { data, loading, error } = useApi<AnyObj>("/evals", []);

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (error) return <div style={{ color: "var(--red)" }}>Error: {error}</div>;

  const evals = data?.evals ?? [];

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Evaluators</h2>
      {evals.length === 0 && <div style={{ color: "var(--text-muted)" }}>No evaluation runs yet.</div>}
      {evals.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: 8 }}>Run</th>
              <th style={{ padding: 8 }}>Dataset</th>
              <th style={{ padding: 8 }}>Pass rate</th>
              <th style={{ padding: 8 }}>Avg score</th>
              <th style={{ padding: 8 }}>Cases</th>
              <th style={{ padding: 8 }}>Date</th>
            </tr>
          </thead>
          <tbody>
            {evals.map((e: AnyObj) => {
              const ok = (e.pass_rate ?? 0) >= (e.threshold ?? 0.7);
              return (
                <tr key={e.run_id}
                  onClick={() => navigate(`/evals/${e.run_id}`)}
                  style={{ cursor: "pointer", borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 8 }}>{e.name}</td>
                  <td style={{ padding: 8, color: "var(--text-muted)" }}>{e.dataset_name ?? "—"}</td>
                  <td style={{ padding: 8, color: ok ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{pct(e.pass_rate)}</td>
                  <td style={{ padding: 8 }}>{e.avg_score != null ? e.avg_score.toFixed(3) : "—"}</td>
                  <td style={{ padding: 8 }}>{e.passed}/{e.total_cases}</td>
                  <td style={{ padding: 8, color: "var(--text-muted)" }}>{e.started_at?.slice(0, 19).replace("T", " ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
