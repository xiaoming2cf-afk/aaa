import { Activity } from "lucide-react";

import { RouteNav } from "./RouteNav";
import type { RouteMetadata } from "./types";

type AppSidebarProps = {
  routes: RouteMetadata[];
  sessionUser?: string;
};

export function AppSidebar({
  routes,
  sessionUser,
}: AppSidebarProps): JSX.Element {
  return (
    <aside className="ops-sidebar" aria-label="Research operations navigation">
      <div className="ops-brand">
        <div className="ops-brand-mark" aria-hidden="true">
          <Activity size={20} strokeWidth={2.4} />
        </div>
        <div>
          <p className="eyebrow">Research Operations</p>
          <h1>Research Agent</h1>
          {sessionUser ? <p>{sessionUser}</p> : null}
        </div>
      </div>
      <RouteNav routes={routes} />
      <details className="ops-legacy" aria-label="Legacy tools">
        <summary>Legacy tools</summary>
        <a href="/workspace">Legacy Workspace</a>
        <a href="/research-agent">Legacy Research</a>
        <a href="/provider-center">Legacy Providers</a>
        <a href="/knowledge-base">Legacy Knowledge</a>
      </details>
    </aside>
  );
}
