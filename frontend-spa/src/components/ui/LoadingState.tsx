export function LoadingState({ title = "Loading" }: { title?: string }): JSX.Element {
  return (
    <div className="ui-state ui-state--loading" role="status" aria-live="polite">
      <strong>{title}</strong>
      <span className="ui-loading-line" aria-hidden="true" />
    </div>
  );
}
