import { AlertTriangle, Bell, Command, HelpCircle, RefreshCw, Search, X } from "lucide-react";

import { Badge, Button } from "../ui";
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
      <div className="ops-command-palette" role="search">
        <Search aria-hidden="true" size={16} />
        <span>Command Palette</span>
        <kbd><Command aria-hidden="true" size={13} /> K</kbd>
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
        <button className="ops-icon-button" type="button" aria-label="Notifications"><Bell aria-hidden="true" size={17} /></button>
        <button className="ops-icon-button" type="button" aria-label="Help"><HelpCircle aria-hidden="true" size={17} /></button>
        <span className="ops-avatar" aria-label="Signed in user">{(currentTeam?.name || currentWorkspace?.name || "VK").slice(0, 2).toUpperCase()}</span>
      </div>
      <div className="ops-command-alert" role="status">
        <AlertTriangle aria-hidden="true" size={17} />
        <strong>Human Intervention Required</strong>
        <span>ARBITER gate blocked the latest run. Review quality, data, and safety gates before publication.</span>
        <Badge tone="warning">{currentRoute.title}</Badge>
        <a href="/app/quality">Review Gate</a>
        <X aria-hidden="true" size={16} />
      </div>
      <div className="ops-command-title sr-only">
        <p className="eyebrow">{currentRoute.eyebrow}</p>
        <h2><CurrentIcon aria-hidden="true" size={24} /> {currentRoute.title}</h2>
        <p className="ops-command-scope">
          {currentWorkspace?.name || "Workspace pending"} / {currentTeam?.name || "No team selected"}
        </p>
      </div>
    </header>
  );
}
