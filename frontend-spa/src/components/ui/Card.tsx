import type { ReactNode } from "react";

export function Card({
  title,
  description,
  children,
  actions,
  className = "",
}: {
  title?: string;
  description?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <article className={`ui-card ${className}`.trim()}>
      {title || description || actions ? (
        <div className="ui-card__header">
          <div>
            {title ? <h3>{title}</h3> : null}
            {description ? <p className="muted">{description}</p> : null}
          </div>
          {actions ? <div className="ui-card__actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </article>
  );
}
