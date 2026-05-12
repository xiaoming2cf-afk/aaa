import type { ReactNode } from "react";

export function AppShell({
  sidebar,
  children,
  inspector,
}: {
  sidebar?: ReactNode;
  children: ReactNode;
  inspector?: ReactNode;
}): JSX.Element {
  return (
    <div className="ui-app-shell">
      {sidebar ? <aside className="ui-app-shell__sidebar">{sidebar}</aside> : null}
      <main className="ui-app-shell__main">{children}</main>
      {inspector ? <aside className="ui-app-shell__inspector">{inspector}</aside> : null}
    </div>
  );
}
