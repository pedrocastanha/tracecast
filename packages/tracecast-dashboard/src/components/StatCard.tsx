import { useState } from "react";

export function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  const [hover, setHover] = useState(false);
  const bar = accent ?? "var(--accent)";
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "relative",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderColor: hover ? "var(--border-strong)" : "var(--border)",
        borderRadius: "var(--radius)",
        padding: "16px 18px",
        overflow: "hidden",
        transition: "border-color .15s ease, transform .15s ease",
        transform: hover ? "translateY(-2px)" : "none",
      }}
    >
      {/* top hairline that lights up on hover */}
      <span
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: bar,
          opacity: hover ? 1 : 0.45,
          transition: "opacity .15s ease",
        }}
      />
      <div style={{ fontSize: 10.5, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10, fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 25, fontWeight: 600, color: "var(--text)", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}>
        {value}
      </div>
    </div>
  );
}
