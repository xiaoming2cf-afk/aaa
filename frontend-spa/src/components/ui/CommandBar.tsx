import type { ReactNode } from "react";

export function CommandBar({ children }: { children: ReactNode }): JSX.Element {
  return <div className="ui-command-bar">{children}</div>;
}
