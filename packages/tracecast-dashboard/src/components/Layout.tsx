import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/traces", label: "Traces" },
  { to: "/models", label: "Models" },
  { to: "/sessions", label: "Sessions" },
  { to: "/projects", label: "Projects" },
];

export function Layout() {
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside style={{ width: 200, background: "var(--surface)", borderRight: "1px solid var(--border)", padding: "20px 0", flexShrink: 0 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--accent)", padding: "0 20px", marginBottom: 24 }}>
          TraceCast
        </h1>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}
              style={({ isActive }) => ({
                padding: "8px 20px", fontSize: 14,
                color: isActive ? "#fff" : "var(--text-muted)",
                background: isActive ? "var(--accent)" : "transparent",
                borderRadius: 6, margin: "0 8px",
              })}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
