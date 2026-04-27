export function CodeBlock({
  children,
  label,
}: {
  children: string;
  label?: string;
}): JSX.Element {
  return (
    <div className="code-block">
      {label ? <div className="code-block-label">{label}</div> : null}
      <pre>{children}</pre>
    </div>
  );
}

export function JsonBlock({ label, value }: { label?: string; value: unknown }): JSX.Element {
  return <CodeBlock label={label}>{JSON.stringify(value || {}, null, 2)}</CodeBlock>;
}
