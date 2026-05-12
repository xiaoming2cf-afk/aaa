import type { ReactNode } from "react";

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }): JSX.Element {
  return (
    <div className="ui-state ui-state--empty" role="status">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="ui-state__action">{action}</div> : null}
    </div>
  );
}
