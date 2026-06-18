import { NavLink, Outlet, useLocation } from "react-router-dom";

// Indexed nav items — the leading number reinforces the "control panel" feel.
const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/traces", label: "Traces" },
  { to: "/models", label: "Models" },
  { to: "/sessions", label: "Sessions" },
  { to: "/projects", label: "Projects" },
  { to: "/evals", label: "Evaluators" },
  { to: "/evals/compare", label: "Compare" },
  { to: "/prompts", label: "Prompts" },
];

export function Layout() {
  const location = useLocation();
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside
        style={{
          width: 232,
          background: "linear-gradient(180deg, var(--surface) 0%, var(--bg-2) 100%)",
          borderRight: "1px solid var(--border)",
          padding: "26px 0 18px",
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          position: "sticky",
          top: 0,
          height: "100vh",
        }}
      >
        {/* Wordmark — lowercase mono with a live signal dot */}
        <div style={{ padding: "0 24px", marginBottom: 30, display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: "50%",
              background: "var(--accent)",
              boxShadow: "0 0 10px var(--accent-glow)",
              flexShrink: 0,
            }}
          />
          <span style={{ fontFamily: "var(--mono)", fontSize: 16, fontWeight: 600, letterSpacing: "-0.02em", color: "var(--text)" }}>
            trace<span style={{ color: "var(--accent)" }}>cast</span>
          </span>
        </div>

        <div style={{ padding: "0 24px 12px", fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-faint)", fontWeight: 600 }}>
          Observability
        </div>

        <nav style={{ display: "flex", flexDirection: "column", gap: 2, padding: "0 12px" }}>
          {NAV_ITEMS.map((item, i) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              style={({ isActive }) => ({
                position: "relative",
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "9px 14px",
                fontSize: 13.5,
                fontWeight: isActive ? 600 : 500,
                color: isActive ? "var(--accent)" : "var(--text-muted)",
                background: isActive ? "var(--accent-dim)" : "transparent",
                borderRadius: "var(--radius-sm)",
                transition: "color .15s ease, background .15s ease",
              })}
            >
              {({ isActive }) => (
                <>
                  {/* Lime indicator bar on the active item */}
                  <span
                    style={{
                      position: "absolute",
                      left: -12,
                      top: "50%",
                      transform: "translateY(-50%)",
                      width: 3,
                      height: isActive ? 18 : 0,
                      background: "var(--accent)",
                      borderRadius: "0 3px 3px 0",
                      boxShadow: isActive ? "0 0 8px var(--accent-glow)" : "none",
                      transition: "height .2s ease",
                    }}
                  />
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: isActive ? "var(--accent)" : "var(--text-faint)", width: 16 }}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div style={{ marginTop: "auto", padding: "0 24px", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px rgba(86,226,154,.5)" }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-faint)" }}>live · v0.3.0</span>
        </div>
      </aside>

      <main style={{ flex: 1, overflow: "auto" }}>
        {/* key on pathname re-triggers the page-enter reveal per route */}
        <div key={location.pathname} className="page-enter" style={{ padding: "28px 32px", maxWidth: 1320, margin: "0 auto" }}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
