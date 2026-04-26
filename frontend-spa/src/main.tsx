import React, { Suspense, createContext, lazy, useContext, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { apiFetch } from "./api";
import { ErrorState, LoadingState } from "./components/StatusPrimitives";
import { KnowledgePage } from "./pages/KnowledgePage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { QualityPage } from "./pages/QualityPage";
import { ResearchPage } from "./pages/ResearchPage";
import { TeamLibraryPage } from "./pages/TeamLibraryPage";
import "./styles.css";

type Workspace = { id: string; name: string; description: string };
type Team = { id: string; name: string; role: string };
type RouteMetadata = {
  path: string;
  navLabel: string;
  title: string;
  eyebrow: string;
};

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
  { path: "/research", navLabel: "Research", title: "Research Runs", eyebrow: "Command Queue" },
  { path: "/data-lab-agent", navLabel: "Data Lab Agent", title: "Data Lab Agent", eyebrow: "Analysis Runtime" },
  { path: "/team-library", navLabel: "Team Library", title: "Team Library", eyebrow: "Published Artifacts" },
  { path: "/knowledge", navLabel: "Knowledge", title: "Knowledge Base", eyebrow: "Workspace Memory" },
  { path: "/providers", navLabel: "Providers", title: "Runtime Providers", eyebrow: "Operations Scope" },
  { path: "/quality", navLabel: "Quality", title: "Quality Gates", eyebrow: "Delivery Control" },
];

const queryClient = new QueryClient();
const AppStateContext = createContext<AppState | null>(null);

function metadataForPath(pathname: string): RouteMetadata {
  const normalizedPath = pathname === "/" ? "/research" : pathname;
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
      <div className="shell">
        <aside className="sidebar">
          <div className="brand-block">
            <p className="eyebrow">Research Operations</p>
            <h1>Research Agent</h1>
            <p className="muted">{sessionQuery.data?.user?.full_name || sessionQuery.data?.user?.email}</p>
          </div>
          <label className="field">
            <span>Workspace</span>
            <select value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
              {state.workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Team</span>
            <select value={teamId} onChange={(event) => setTeamId(event.target.value)}>
              <option value="">No team</option>
              {state.teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
              ))}
            </select>
          </label>
          <nav className="nav">
            {ROUTE_METADATA.map((route) => (
              <NavLink key={route.path} to={route.path} className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                {route.navLabel}
              </NavLink>
            ))}
          </nav>
          <div className="legacy-links">
            <a href="/workspace">Legacy Workspace</a>
            <a href="/research-agent">Legacy Research</a>
            <a href="/provider-center">Legacy Providers</a>
            <a href="/knowledge-base">Legacy Knowledge</a>
          </div>
        </aside>
        <main className="main">
          <header className="main-header">
            <div>
              <p className="eyebrow">{currentRoute.eyebrow}</p>
              <h2>{currentRoute.title}</h2>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                void queryClientInstance.invalidateQueries();
              }}
            >
              Refresh All
            </button>
          </header>
          <Outlet />
        </main>
      </div>
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
            <Route index element={<Navigate to="/research" replace />} />
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
