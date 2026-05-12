import type { ReactNode } from "react";

export function Tabs({ children, label }: { children: ReactNode; label?: string }): JSX.Element {
  return (
    <div className="ui-tabs" role="tablist" aria-label={label || "Tabs"}>
      {children}
    </div>
  );
}

export function TabButton({ active, children, onClick }: { active?: boolean; children: ReactNode; onClick?: () => void }): JSX.Element {
  return (
    <button className={`ui-tab${active ? " is-active" : ""}`} type="button" role="tab" aria-selected={Boolean(active)} onClick={onClick}>
      {children}
    </button>
  );
}
