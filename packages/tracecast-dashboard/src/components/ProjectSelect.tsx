import { useApi } from "../hooks/useApi";

interface FilterOptions {
  project_names: string[];
}

const selectStyle = {
  padding: "8px 14px",
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  borderRadius: "var(--radius-sm)",
  fontSize: 13,
  minWidth: 180,
} as const;

export function ProjectSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const { data: opts } = useApi<FilterOptions>("/filter-options", []);
  const names = opts?.project_names ?? [];

  if (names.length <= 1) return null;

  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} style={selectStyle}>
      <option value="">All projects</option>
      {names.map((n) => (
        <option key={n} value={n}>{n}</option>
      ))}
    </select>
  );
}
