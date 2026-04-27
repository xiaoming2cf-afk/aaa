import type { ReactNode } from "react";

export function Field({
  children,
  className = "",
  help,
  label,
  span = false,
}: {
  children: ReactNode;
  className?: string;
  help?: ReactNode;
  label: ReactNode;
  span?: boolean;
}): JSX.Element {
  return (
    <label className={`ops-field ${span ? "ops-field-span" : ""} ${className}`.trim()}>
      <span>{label}</span>
      {children}
      {help ? <small>{help}</small> : null}
    </label>
  );
}
