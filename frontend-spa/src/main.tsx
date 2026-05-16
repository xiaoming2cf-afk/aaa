import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Brain, Database, Gauge, LayoutDashboard, Library, LogIn, Server } from "lucide-react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { apiFetch } from "./api";
import { ErrorState, LoadingState } from "./components/StatusPrimitives";
import { AppChrome } from "./components/layout";
import type { RouteMetadata, Team, Workspace } from "./components/layout";
import { ActionLink } from "./components/ui";
import { I18nProvider, useI18n } from "./i18n";
import { DataLabAgentPage } from "./pages/DataLabAgentPage";
import { DataLabHubPage } from "./pages/DataLabHubPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { OverviewPage } from "./pages/OverviewPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { QualityPage } from "./pages/QualityPage";
import { ResearchPage } from "./pages/ResearchPage";
import { TeamLibraryPage } from "./pages/TeamLibraryPage";
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

const ROUTE_METADATA: RouteMetadata[] = [
  { path: "/overview", navLabel: "Overview", navKey: "nav.overview", title: "Overview", titleKey: "nav.overview", eyebrow: "Workspace Command Center", eyebrowKey: "route.overview.eyebrow", icon: LayoutDashboard },
  { path: "/research", navLabel: "Research", navKey: "nav.research", title: "Research Runs", titleKey: "nav.research", eyebrow: "Command Queue", eyebrowKey: "route.research.eyebrow", icon: Brain },
  { path: "/data-lab", navLabel: "Data Lab", navKey: "nav.dataLab", title: "Data Lab", titleKey: "nav.dataLab", eyebrow: "Workspace Data Lab", eyebrowKey: "route.dataLab.eyebrow", icon: Database },
  { path: "/data-lab-agent", navLabel: "Data Lab Agent", navKey: "nav.dataLabAgent", title: "Data Lab Agent", titleKey: "nav.dataLabAgent", eyebrow: "Analysis Runtime", eyebrowKey: "route.dataLabAgent.eyebrow", icon: Database },
  { path: "/team-library", navLabel: "Team Library", navKey: "nav.teamLibrary", title: "Team Library", titleKey: "nav.teamLibrary", eyebrow: "Published Artifacts", eyebrowKey: "route.teamLibrary.eyebrow", icon: Library },
  { path: "/knowledge", navLabel: "Knowledge", navKey: "nav.knowledge", title: "Knowledge Base", titleKey: "nav.knowledge", eyebrow: "Workspace Memory", eyebrowKey: "route.knowledge.eyebrow", icon: BookOpen },
  { path: "/providers", navLabel: "Providers", navKey: "nav.providers", title: "Runtime Providers", titleKey: "nav.providers", eyebrow: "Operations Scope", eyebrowKey: "route.providers.eyebrow", icon: Server },
  { path: "/quality", navLabel: "Quality", navKey: "nav.quality", title: "Quality Gates", titleKey: "nav.quality", eyebrow: "Delivery Control", eyebrowKey: "route.quality.eyebrow", icon: Gauge },
];

const queryClient = new QueryClient();
const AppStateContext = createContext<AppState | null>(null);

function metadataForPath(pathname: string): RouteMetadata {
  const pathWithoutBase = pathname === "/app"
    ? "/"
    : pathname.startsWith("/app/")
      ? pathname.slice(4)
      : pathname;
  const normalizedPath = pathWithoutBase === "/" ? "/overview" : pathWithoutBase;
  return ROUTE_METADATA.find((route) => route.path === normalizedPath)
    || ROUTE_METADATA.find((route) => normalizedPath.startsWith(`${route.path}/`))
    || ROUTE_METADATA[0];
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
  const { t } = useI18n();
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
          title={t("app.sessionExpired")}
          description={t("app.sessionExpiredDescription")}
          action={<ActionLink href="/#auth-panel" icon={<LogIn size={16} />} variant="primary">{t("app.returnToLogin")}</ActionLink>}
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
      <I18nProvider>
        <BrowserRouter basename="/app">
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<OverviewPage useAppState={useSpaState} />} />
              <Route path="/research" element={<ResearchPage useAppState={useSpaState} />} />
              <Route path="/data-lab" element={<DataLabHubPage useAppState={useSpaState} />} />
              <Route path="/data-lab/:section" element={<DataLabHubPage useAppState={useSpaState} />} />
              <Route
                path="/data-lab-agent"
                element={<DataLabAgentPage useAppState={useSpaState} />}
              />
              <Route path="/team-library" element={<TeamLibraryPage useAppState={useSpaState} />} />
              <Route path="/knowledge" element={<KnowledgePage useAppState={useSpaState} />} />
              <Route path="/providers" element={<ProvidersPage useAppState={useSpaState} />} />
              <Route path="/quality" element={<QualityPage useAppState={useSpaState} />} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </I18nProvider>
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
