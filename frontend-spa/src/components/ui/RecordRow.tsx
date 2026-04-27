import type { ButtonHTMLAttributes, ReactNode } from "react";

type RecordRowProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  meta?: ReactNode;
  selected?: boolean;
  status?: ReactNode;
  title: ReactNode;
};

export function RecordRow({
  children,
  className = "",
  meta,
  selected = false,
  status,
  title,
  type = "button",
  ...props
}: RecordRowProps): JSX.Element {
  return (
    <button
      {...props}
      className={`record-row ${selected ? "selected" : ""} ${className}`.trim()}
      type={type}
    >
      <span className="record-row-main">
        <strong>{title}</strong>
        {children ? <span>{children}</span> : null}
        {meta ? <small>{meta}</small> : null}
      </span>
      {status ? <span className="record-row-status">{status}</span> : null}
    </button>
  );
}
