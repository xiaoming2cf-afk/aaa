import type { ReactNode } from "react";

export function ErrorState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }): JSX.Element {
  return (
    <div className="ui-state ui-state--error" role="alert">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="ui-state__action">{action}</div> : null}
    </div>
  );
}
