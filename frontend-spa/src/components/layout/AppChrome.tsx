import type { ReactNode } from "react";

import { AppSidebar } from "./AppSidebar";
import { CommandBar } from "./CommandBar";
import { GlobalStatusStrip } from "./GlobalStatusStrip";
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
        workspaces={workspaces}
        teams={teams}
        workspaceId={workspaceId}
        onWorkspaceChange={onWorkspaceChange}
        teamId={teamId}
        onTeamChange={onTeamChange}
      />
      <main className="ops-main">
        <CommandBar
          currentRoute={currentRoute}
          currentWorkspace={currentWorkspace}
          currentTeam={currentTeam}
          onRefreshAll={onRefreshAll}
        />
        <GlobalStatusStrip currentWorkspace={currentWorkspace} currentTeam={currentTeam} />
        {children}
      </main>
    </div>
  );
}
