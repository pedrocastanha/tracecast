import { useApi } from "../hooks/useApi";

interface FilterOptions {
  project_names: string[];
  project_ids: Record<string, string[]>;
  user_ids: Record<string, string[]>;
}

export interface CascadeFilterValue {
  projectName: string;
  projectId: string;
  userId: string;
}

const selectStyle = {
  padding: "8px 12px",
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  borderRadius: "var(--radius-sm)",
  fontSize: 13,
  minWidth: 160,
} as const;

const clearBtn = {
  padding: "8px 12px",
  border: "1px solid var(--border)",
  background: "transparent",
  color: "var(--text-faint)",
  borderRadius: "var(--radius-sm)",
  cursor: "pointer",
  fontFamily: "var(--mono)",
  fontSize: 12,
} as const;

interface Props {
  value: CascadeFilterValue;
  onChange: (v: CascadeFilterValue) => void;
  showUserFilter?: boolean;
}

export function CascadeFilter({ value, onChange, showUserFilter = false }: Props) {
  const { data: opts } = useApi<FilterOptions>("/filter-options", []);

  if (!opts || opts.project_names.length === 0) return null;

  const availableProjectIds =
    value.projectName && opts.project_ids?.[value.projectName]
      ? opts.project_ids[value.projectName]
      : [];

  const availableUserIds =
    value.projectId && opts.user_ids?.[value.projectId]
      ? opts.user_ids[value.projectId]
      : [];

  const hasFilters = value.projectName || value.projectId || value.userId;

  function handleProjectName(v: string) {
    onChange({ projectName: v, projectId: "", userId: "" });
  }
  function handleProjectId(v: string) {
    onChange({ ...value, projectId: v, userId: "" });
  }
  function handleUserId(v: string) {
    onChange({ ...value, userId: v });
  }
  function handleClear() {
    onChange({ projectName: "", projectId: "", userId: "" });
  }

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <select value={value.projectName} onChange={(e) => handleProjectName(e.target.value)} style={selectStyle}>
        <option value="">All projects</option>
        {opts.project_names.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>

      {value.projectName && availableProjectIds.length > 0 && (
        <select value={value.projectId} onChange={(e) => handleProjectId(e.target.value)} style={selectStyle}>
          <option value="">All filials</option>
          {availableProjectIds.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      )}

      {showUserFilter && value.projectId && availableUserIds.length > 0 && (
        <select value={value.userId} onChange={(e) => handleUserId(e.target.value)} style={selectStyle}>
          <option value="">All users</option>
          {availableUserIds.map((uid) => <option key={uid} value={uid}>{uid}</option>)}
        </select>
      )}

      {hasFilters && (
        <button onClick={handleClear} style={clearBtn}>clear</button>
      )}
    </div>
  );
}
