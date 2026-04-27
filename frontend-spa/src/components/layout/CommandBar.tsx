import { RefreshCw, Users, Wifi } from "lucide-react";

import { Button } from "../ui";
import type { RouteMetadata, Team, Workspace } from "./types";

type CommandBarProps = {
  currentRoute: RouteMetadata;
  currentWorkspace?: Workspace;
  currentTeam?: Team;
  onRefreshAll: () => void;
};

export function CommandBar({
  currentRoute,
  currentWorkspace,
  currentTeam,
  onRefreshAll,
}: CommandBarProps): JSX.Element {
  const CurrentIcon = currentRoute.icon;

  return (
    <header className="ops-command-bar">
      <div className="ops-command-title">
        <p className="eyebrow">{currentRoute.eyebrow}</p>
        <h2><CurrentIcon aria-hidden="true" size={24} /> {currentRoute.title}</h2>
      </div>
      <div className="ops-command-actions">
        <div className="ops-global-state" aria-label="Current workspace">
          <Wifi aria-hidden="true" size={16} />
          <span>{currentWorkspace?.name || "Workspace pending"}</span>
        </div>
        <div className="ops-global-state" aria-label="Current team">
          <Users aria-hidden="true" size={16} />
          <span>{currentTeam?.name || "No team"}</span>
        </div>
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
