import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  loading?: boolean;
  variant?: ButtonVariant;
};

export function Button({
  children,
  className = "",
  disabled,
  icon,
  loading = false,
  type = "button",
  variant = "secondary",
  ...props
}: ButtonProps): JSX.Element {
  return (
    <button
      {...props}
      className={`ops-button ops-button-${variant} ${className}`.trim()}
      disabled={disabled || loading}
      type={type}
    >
      {icon ? <span className="ops-button-icon" aria-hidden="true">{icon}</span> : null}
      <span>{loading ? "Working" : children}</span>
    </button>
  );
}

export function ActionLink({
  children,
  className = "",
  icon,
  variant = "secondary",
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  icon?: ReactNode;
  variant?: ButtonVariant;
}): JSX.Element {
  return (
    <a {...props} className={`ops-button ops-button-${variant} ${className}`.trim()}>
      {icon ? <span className="ops-button-icon" aria-hidden="true">{icon}</span> : null}
      <span>{children}</span>
    </a>
  );
}
