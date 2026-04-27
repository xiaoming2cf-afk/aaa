import { Activity } from "lucide-react";

import { RouteNav } from "./RouteNav";
import { ScopePanel } from "./ScopePanel";
import type { RouteMetadata, Team, Workspace } from "./types";

type AppSidebarProps = {
  routes: RouteMetadata[];
  sessionUser?: string;
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  onWorkspaceChange: (value: string) => void;
  teamId: string;
  onTeamChange: (value: string) => void;
};

export function AppSidebar({
  routes,
  sessionUser,
  workspaces,
  teams,
  workspaceId,
  onWorkspaceChange,
  teamId,
  onTeamChange,
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
          <p>{sessionUser}</p>
        </div>
      </div>
      <ScopePanel
        workspaces={workspaces}
        teams={teams}
        workspaceId={workspaceId}
        onWorkspaceChange={onWorkspaceChange}
        teamId={teamId}
        onTeamChange={onTeamChange}
      />
      <RouteNav routes={routes} />
      <div className="ops-legacy" aria-label="Legacy tools">
        <a href="/workspace">Legacy Workspace</a>
        <a href="/research-agent">Legacy Research</a>
        <a href="/provider-center">Legacy Providers</a>
        <a href="/knowledge-base">Legacy Knowledge</a>
      </div>
    </aside>
  );
}
