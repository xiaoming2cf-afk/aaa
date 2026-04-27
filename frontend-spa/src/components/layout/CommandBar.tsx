import { RefreshCw } from "lucide-react";

import { Button } from "../ui";
import { ScopePanel } from "./ScopePanel";
import type { RouteMetadata, Team, Workspace } from "./types";

type CommandBarProps = {
  currentRoute: RouteMetadata;
  currentWorkspace?: Workspace;
  currentTeam?: Team;
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  onWorkspaceChange: (value: string) => void;
  teamId: string;
  onTeamChange: (value: string) => void;
  onRefreshAll: () => void;
};

export function CommandBar({
  currentRoute,
  currentWorkspace,
  currentTeam,
  workspaces,
  teams,
  workspaceId,
  onWorkspaceChange,
  teamId,
  onTeamChange,
  onRefreshAll,
}: CommandBarProps): JSX.Element {
  const CurrentIcon = currentRoute.icon;

  return (
    <header className="ops-command-bar">
      <div className="ops-command-title">
        <p className="eyebrow">{currentRoute.eyebrow}</p>
        <h2><CurrentIcon aria-hidden="true" size={24} /> {currentRoute.title}</h2>
        <p className="ops-command-scope">
          {currentWorkspace?.name || "Workspace pending"} / {currentTeam?.name || "No team selected"}
        </p>
      </div>
      <div className="ops-command-actions">
        <ScopePanel
          workspaces={workspaces}
          teams={teams}
          workspaceId={workspaceId}
          onWorkspaceChange={onWorkspaceChange}
          teamId={teamId}
          onTeamChange={onTeamChange}
        />
        <Button
          type="button"
          variant="ghost"
          icon={<RefreshCw size={16} aria-hidden="true" />}
          onClick={onRefreshAll}
        >
          Refresh All
        </Button>
      </div>
    </header>
  );
}
