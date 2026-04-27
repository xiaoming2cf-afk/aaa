import React, { Suspense, createContext, lazy, useContext, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Brain, Database, Gauge, LayoutDashboard, Library, Server } from "lucide-react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { apiFetch } from "./api";
import { ErrorState, LoadingState } from "./components/StatusPrimitives";
import { AppChrome } from "./components/layout";
import type { RouteMetadata, Team, Workspace } from "./components/layout";
import { KnowledgePage } from "./pages/KnowledgePage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { QualityPage } from "./pages/QualityPage";
import { ResearchPage } from "./pages/ResearchPage";
import { TeamLibraryPage } from "./pages/TeamLibraryPage";
import { OverviewPage } from "./features/workbench/OverviewPage";
import "./styles.css";

type AppState = {
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  setWorkspaceId: (value: string) => void;
  teamId: string;
  setTeamId: (value: string) => void;
  refreshShared: () => void;
};

const STORAGE_KEYS = {
  workspaceId: "spa-workspace-id",
  teamId: "spa-team-id",
} as const;

const DataLabAgentPage = lazy(() => import("./pages/DataLabAgentPage").then((module) => ({
  default: module.DataLabAgentPage,
})));

const ROUTE_METADATA: RouteMetadata[] = [
  { path: "/overview", navLabel: "Overview", title: "Workbench Overview", eyebrow: "Institutional Terminal", icon: LayoutDashboard },
  { path: "/research", navLabel: "Research", title: "Research Runs", eyebrow: "Command Queue", icon: Brain },
  { path: "/data-lab-agent", navLabel: "Data Lab Agent", title: "Data Lab Agent", eyebrow: "Analysis Runtime", icon: Database },
  { path: "/team-library", navLabel: "Team Library", title: "Team Library", eyebrow: "Published Artifacts", icon: Library },
  { path: "/knowledge", navLabel: "Knowledge", title: "Knowledge Base", eyebrow: "Workspace Memory", icon: BookOpen },
  { path: "/providers", navLabel: "Providers", title: "Runtime Providers", eyebrow: "Operations Scope", icon: Server },
  { path: "/quality", navLabel: "Quality", title: "Quality Gates", eyebrow: "Delivery Control", icon: Gauge },
];

const queryClient = new QueryClient();
const AppStateContext = createContext<AppState | null>(null);

function metadataForPath(pathname: string): RouteMetadata {
  const normalizedPath = pathname === "/" ? "/overview" : pathname;
  return ROUTE_METADATA.find((route) => route.path === normalizedPath) || ROUTE_METADATA[0];
}

function useAppState(): AppState {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("App state is unavailable.");
  }
  return value;
}

export function AppShell(): JSX.Element {
  const queryClientInstance = useQueryClient();
  const location = useLocation();
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: () => apiFetch<{ user: { full_name: string; email: string } }>("/api/auth/me"),
  });
  const workspacesQuery = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => apiFetch<{ items: Workspace[] }>("/api/workspaces"),
  });
  const teamsQuery = useQuery({
    queryKey: ["teams"],
    queryFn: () => apiFetch<{ items: Team[] }>("/api/teams"),
  });
  const workspaces = useMemo(() => workspacesQuery.data?.items || [], [workspacesQuery.data]);
  const teams = useMemo(() => teamsQuery.data?.items || [], [teamsQuery.data]);
  const currentRoute = metadataForPath(location.pathname);
  const [workspaceId, setWorkspaceId] = useState<string>(() => localStorage.getItem(STORAGE_KEYS.workspaceId) || "");
  const [teamId, setTeamId] = useState<string>(() => localStorage.getItem(STORAGE_KEYS.teamId) || "");

  useEffect(() => {
    if (!workspacesQuery.isSuccess) {
      return;
    }
    const workspaceExists = workspaces.some((workspace) => workspace.id === workspaceId);
    const nextWorkspaceId = workspaceExists ? workspaceId : workspaces[0]?.id || "";
    if (nextWorkspaceId !== workspaceId) {
      setWorkspaceId(nextWorkspaceId);
    }
  }, [workspaceId, workspaces, workspacesQuery.isSuccess]);

  useEffect(() => {
    if (!teamsQuery.isSuccess) {
      return;
    }
    const teamExists = teams.some((team) => team.id === teamId);
    const nextTeamId = teamExists ? teamId : teams[0]?.id || "";
    if (nextTeamId !== teamId) {
      setTeamId(nextTeamId);
    }
  }, [teamId, teams, teamsQuery.isSuccess]);

  useEffect(() => {
    if (workspaceId) {
      localStorage.setItem(STORAGE_KEYS.workspaceId, workspaceId);
      return;
    }
    localStorage.removeItem(STORAGE_KEYS.workspaceId);
  }, [workspaceId]);

  useEffect(() => {
    if (teamId) {
      localStorage.setItem(STORAGE_KEYS.teamId, teamId);
      return;
    }
    localStorage.removeItem(STORAGE_KEYS.teamId);
  }, [teamId]);

  const state = useMemo<AppState>(() => ({
    workspaces,
    teams,
    workspaceId,
    setWorkspaceId,
    teamId,
    setTeamId,
    refreshShared: () => {
      void queryClientInstance.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClientInstance.invalidateQueries({ queryKey: ["teams"] });
    },
  }), [queryClientInstance, teamId, teams, workspaceId, workspaces]);
  const currentWorkspace = workspaces.find((workspace) => workspace.id === workspaceId);
  const currentTeam = teams.find((team) => team.id === teamId);

  if (sessionQuery.isLoading) {
    return (
      <div className="screen-message">
        <LoadingState title="Loading session" description="Checking your research operations context." />
      </div>
    );
  }

  if (sessionQuery.isError) {
    return (
      <div className="screen-message">
        <ErrorState
          title="Session expired"
          description="Open the legacy login page and sign in again."
        />
      </div>
    );
  }

  return (
    <AppStateContext.Provider value={state}>
      <AppChrome
        routes={ROUTE_METADATA}
        currentRoute={currentRoute}
        sessionUser={sessionQuery.data?.user?.full_name || sessionQuery.data?.user?.email}
        workspaces={state.workspaces}
        teams={state.teams}
        workspaceId={workspaceId}
        onWorkspaceChange={setWorkspaceId}
        teamId={teamId}
        onTeamChange={setTeamId}
        currentWorkspace={currentWorkspace}
        currentTeam={currentTeam}
        onRefreshAll={() => {
          void queryClientInstance.invalidateQueries();
        }}
      >
        <Outlet />
      </AppChrome>
    </AppStateContext.Provider>
  );
}

export function useSpaState(): AppState {
  return useAppState();
}

export function App(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<OverviewPage useAppState={useSpaState} />} />
            <Route path="/research" element={<ResearchPage useAppState={useSpaState} />} />
            <Route
              path="/data-lab-agent"
              element={(
                <Suspense fallback={<LoadingState title="Loading Data Lab Agent" description="Preparing the analysis runtime." />}>
                  <DataLabAgentPage useAppState={useSpaState} />
                </Suspense>
              )}
            />
            <Route path="/team-library" element={<TeamLibraryPage useAppState={useSpaState} />} />
            <Route path="/knowledge" element={<KnowledgePage useAppState={useSpaState} />} />
            <Route path="/providers" element={<ProvidersPage useAppState={useSpaState} />} />
            <Route path="/quality" element={<QualityPage useAppState={useSpaState} />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
