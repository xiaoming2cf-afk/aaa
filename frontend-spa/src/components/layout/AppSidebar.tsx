import { Activity, Box, CreditCard, Database, FlaskConical, KeyRound, NotebookTabs, Settings2 } from "lucide-react";

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
          <h1>ARBITER</h1>
          <p>Research Ops Console</p>
          {sessionUser ? <p>{sessionUser}</p> : null}
        </div>
      </div>
      <RouteNav routes={routes} />
      <nav className="ops-nav ops-nav-secondary" aria-label="Operational tools">
        <a className="ops-nav-link" href="/app/research"><Activity aria-hidden="true" size={18} /><span>Runs</span></a>
        <a className="ops-nav-link" href="/app/quality"><FlaskConical aria-hidden="true" size={18} /><span>Experiments</span></a>
        <a className="ops-nav-link" href="/app/knowledge"><Database aria-hidden="true" size={18} /><span>Datasets</span></a>
        <a className="ops-nav-link" href="/app/providers"><Box aria-hidden="true" size={18} /><span>Models</span></a>
        <a className="ops-nav-link" href="/app/data-lab-agent"><NotebookTabs aria-hidden="true" size={18} /><span>Notebooks</span></a>
      </nav>
      <nav className="ops-nav ops-nav-secondary ops-nav-admin" aria-label="Administration">
        <a className="ops-nav-link" href="/app/providers"><Settings2 aria-hidden="true" size={18} /><span>Settings</span></a>
        <a className="ops-nav-link" href="/app/providers"><KeyRound aria-hidden="true" size={18} /><span>Access</span></a>
        <a className="ops-nav-link" href="/app/providers"><CreditCard aria-hidden="true" size={18} /><span>Billing</span></a>
      </nav>
      <div className="ops-system-card" aria-label="System health">
        <span>System Health</span>
        <strong>All systems operational</strong>
        <a href="/app/quality">View Status</a>
      </div>
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
