import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { apiFetch } from "./api";
import { KnowledgePage } from "./pages/KnowledgePage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { QualityPage } from "./pages/QualityPage";
import { ResearchPage } from "./pages/ResearchPage";
import { TeamLibraryPage } from "./pages/TeamLibraryPage";
import "./styles.css";

type Workspace = { id: string; name: string; description: string; };
type Team = { id: string; name: string; role: string; };

type AppState = {
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  setWorkspaceId: (value: string) => void;
  teamId: string;
  setTeamId: (value: string) => void;
  refreshShared: () => void;
};

const AppStateContext = createContext<AppState | null>(null);

function useAppState(): AppState {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("App state is unavailable.");
  }
  return value;
}

function AppShell(): JSX.Element {
  const queryClient = useQueryClient();
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
  const [workspaceId, setWorkspaceId] = useState<string>(localStorage.getItem("spa-workspace-id") || "");
  const [teamId, setTeamId] = useState<string>(localStorage.getItem("spa-team-id") || "");

  useEffect(() => {
    if (!workspaceId && workspacesQuery.data?.items?.length) {
      setWorkspaceId(workspacesQuery.data.items[0].id);
    }
  }, [workspaceId, workspacesQuery.data]);

  useEffect(() => {
    if (!teamId && teamsQuery.data?.items?.length) {
      setTeamId(teamsQuery.data.items[0].id);
    }
  }, [teamId, teamsQuery.data]);

  useEffect(() => {
    if (workspaceId) {
      localStorage.setItem("spa-workspace-id", workspaceId);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (teamId) {
      localStorage.setItem("spa-team-id", teamId);
    }
  }, [teamId]);

  const state = useMemo<AppState>(() => ({
    workspaces: workspacesQuery.data?.items || [],
    teams: teamsQuery.data?.items || [],
    workspaceId,
    setWorkspaceId,
    teamId,
    setTeamId,
    refreshShared: () => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  }), [queryClient, teamId, teamsQuery.data, workspaceId, workspacesQuery.data]);

  if (sessionQuery.isLoading) {
    return <div className="screen-message">Loading session…</div>;
  }

  if (sessionQuery.isError) {
    return <div className="screen-message">Session expired. Open the legacy login page and sign in again.</div>;
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
            <NavLink to="/research" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>Research</NavLink>
            <NavLink to="/team-library" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>Team Library</NavLink>
            <NavLink to="/knowledge" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>Knowledge</NavLink>
            <NavLink to="/providers" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>Providers</NavLink>
            <NavLink to="/quality" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>Quality</NavLink>
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
              <p className="eyebrow">Dual Track SPA</p>
              <h2>{location.pathname.replace("/app/", "").replace("-", " ") || "research"}</h2>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                void queryClient.invalidateQueries();
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

const queryClient = new QueryClient();

function App(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/research" replace />} />
            <Route path="/research" element={<ResearchPage useAppState={useSpaState} />} />
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
