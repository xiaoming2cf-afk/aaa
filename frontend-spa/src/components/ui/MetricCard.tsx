export function MetricCard({ label, value, detail }: { label: string; value: string | number; detail?: string }): JSX.Element {
  return (
    <article className="ui-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <p>{detail}</p> : null}
    </article>
  );
}
