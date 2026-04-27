import type { ReactNode } from "react";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }): JSX.Element {
  return <span className={`ops-badge ops-badge-${tone}`}>{children}</span>;
}
