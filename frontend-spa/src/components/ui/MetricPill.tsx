import type { ReactNode } from "react";

export function MetricPill({
  label,
  tone = "neutral",
  value,
}: {
  label: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  value: ReactNode;
}): JSX.Element {
  return (
    <span className={`metric-pill metric-pill-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}
