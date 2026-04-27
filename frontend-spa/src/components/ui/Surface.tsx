import type { ReactNode } from "react";

type SurfaceTone = "default" | "emphasis" | "muted" | "warning" | "danger" | "success";

export function Surface({
  actions,
  children,
  className = "",
  description,
  eyebrow,
  span = false,
  title,
  tone = "default",
}: {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  description?: ReactNode;
  eyebrow?: string;
  span?: boolean;
  title?: ReactNode;
  tone?: SurfaceTone;
}): JSX.Element {
  return (
    <section className={`ops-surface ops-surface-${tone} ${span ? "ops-surface-span" : ""} ${className}`.trim()}>
      {title || actions || eyebrow || description ? (
        <div className="ops-surface-header">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            {title ? <h3>{title}</h3> : null}
            {description ? <p>{description}</p> : null}
          </div>
          {actions ? <div className="ops-surface-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
