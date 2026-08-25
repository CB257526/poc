import type { ReactNode } from "react";

export function Hero({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="hero">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  );
}

export function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint ? <div className="hint">{hint}</div> : null}
    </div>
  );
}

export function StatusPill({ kind, children }: { kind: "done" | "warn" | "bad" | "idle"; children: ReactNode }) {
  return <span className={`status ${kind}`}>{children}</span>;
}
