import type { ReactNode } from "react";

export function InspectorPanel({ title, children }: { title: string; children: ReactNode }): JSX.Element {
  return (
    <aside className="ui-inspector">
      <h2>{title}</h2>
      {children}
    </aside>
  );
}
