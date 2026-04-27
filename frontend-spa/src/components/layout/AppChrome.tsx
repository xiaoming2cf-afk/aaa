import type { ReactNode } from "react";

import { AppSidebar } from "./AppSidebar";
import { CommandBar } from "./CommandBar";
import type { RouteMetadata, Team, Workspace } from "./types";

type AppChromeProps = {
  routes: RouteMetadata[];
  currentRoute: RouteMetadata;
  sessionUser?: string;
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  onWorkspaceChange: (value: string) => void;
  teamId: string;
  onTeamChange: (value: string) => void;
  currentWorkspace?: Workspace;
  currentTeam?: Team;
  onRefreshAll: () => void;
  children: ReactNode;
};

export function AppChrome({
  routes,
  currentRoute,
  sessionUser,
  workspaces,
  teams,
  workspaceId,
  onWorkspaceChange,
  teamId,
  onTeamChange,
  currentWorkspace,
  currentTeam,
  onRefreshAll,
  children,
}: AppChromeProps): JSX.Element {
  return (
    <div className="ops-layout">
      <AppSidebar
        routes={routes}
        sessionUser={sessionUser}
      />
      <div className="ops-workbench">
        <CommandBar
          currentRoute={currentRoute}
          currentWorkspace={currentWorkspace}
          currentTeam={currentTeam}
          workspaces={workspaces}
          teams={teams}
          workspaceId={workspaceId}
          onWorkspaceChange={onWorkspaceChange}
          teamId={teamId}
          onTeamChange={onTeamChange}
          onRefreshAll={onRefreshAll}
        />
        <main className="ops-main">
          <div className="ops-main-inner">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
