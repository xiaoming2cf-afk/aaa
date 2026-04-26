type StatusPrimitiveProps = {
  title: string;
  description?: string;
  action?: JSX.Element;
};

export function LoadingState({ title, description }: StatusPrimitiveProps): JSX.Element {
  return (
    <div className="status-panel" role="status" aria-live="polite">
      <span className="status-kicker">Loading</span>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      <div className="loading-bar" aria-hidden="true">
        <span />
      </div>
    </div>
  );
}

export function ErrorState({ title, description, action }: StatusPrimitiveProps): JSX.Element {
  return (
    <div className="status-panel status-panel-error" role="alert">
      <span className="status-kicker">Error</span>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {action ? <div className="action-row">{action}</div> : null}
    </div>
  );
}

export function EmptyState({ title, description, action }: StatusPrimitiveProps): JSX.Element {
  return (
    <div className="status-panel status-panel-empty" role="status">
      <span className="status-kicker">Empty</span>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {action ? <div className="action-row">{action}</div> : null}
    </div>
  );
}

export function InlineErrorState({ title, description, action }: StatusPrimitiveProps): JSX.Element {
  return (
    <div className="list-card static-card inline-state inline-state-error" role="alert">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="action-row">{action}</div> : null}
    </div>
  );
}

export function InlineEmptyState({ title, description, action }: StatusPrimitiveProps): JSX.Element {
  return (
    <div className="list-card static-card inline-state" role="status">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="action-row">{action}</div> : null}
    </div>
  );
}
