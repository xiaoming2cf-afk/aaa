import { Bot, Clock3, Database, FlaskConical, History, PlaySquare, Settings2, Table2 } from "lucide-react";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api";
import { InlineEmptyState, InlineErrorState, LoadingState } from "../components/StatusPrimitives";

type UseAppState = () => {
  workspaceId: string;
};

type HistoryItem = {
  id?: string;
  run_id?: string;
  title?: string;
  status?: string;
  summary?: string;
  created_at?: string;
  updated_at?: string;
  finished_at?: string;
};

type DataLabHistoryResponse = {
  processing?: HistoryItem[];
  models?: HistoryItem[];
  optimization?: HistoryItem[];
  agent_sessions?: HistoryItem[];
};

type RouteCard = {
  description: string;
  href: string;
  label: string;
  title: string;
  icon: JSX.Element;
};

type RecentItem = HistoryItem & {
  bucket: string;
};

const routeCards: RouteCard[] = [
  {
    description: "Legacy full workbench for dataset upload and inspection.",
    href: "/data-lab",
    icon: <Database aria-hidden="true" />,
    label: "Legacy",
    title: "Dataset Intake",
  },
  {
    description: "Legacy preparation workflow for cleaning and feature work.",
    href: "/data-lab/preparation",
    icon: <Settings2 aria-hidden="true" />,
    label: "Legacy",
    title: "Preparation",
  },
  {
    description: "Legacy model setup and execution surface.",
    href: "/data-lab/model",
    icon: <FlaskConical aria-hidden="true" />,
    label: "Legacy",
    title: "Model Lab",
  },
  {
    description: "Legacy output review and export surface.",
    href: "/data-lab/results",
    icon: <Table2 aria-hidden="true" />,
    label: "Legacy",
    title: "Results",
  },
  {
    description: "Legacy processing, model, and optimization run history.",
    href: "/data-lab/history",
    icon: <History aria-hidden="true" />,
    label: "Legacy",
    title: "History",
  },
  {
    description: "Legacy optimization benchmark and comparison suite.",
    href: "/data-lab/optimization",
    icon: <PlaySquare aria-hidden="true" />,
    label: "Legacy",
    title: "Optimization",
  },
  {
    description: "SPA agentic analysis runtime for dataset conversations.",
    href: "/app/data-lab-agent",
    icon: <Bot aria-hidden="true" />,
    label: "SPA",
    title: "Data Lab Agent",
  },
];

function listOf(value: unknown): HistoryItem[] {
  return Array.isArray(value) ? value.filter((item): item is HistoryItem => Boolean(item && typeof item === "object")) : [];
}

function timestampOf(item: HistoryItem): number {
  const raw = item.updated_at || item.finished_at || item.created_at || "";
  const timestamp = Date.parse(raw);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function summarizeError(error: unknown): string {
  return error && typeof error === "object" && "message" in error
    ? String((error as { message?: unknown }).message)
    : "Data Lab history could not be loaded.";
}

export function DataLabHubPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();
  const historyQuery = useQuery({
    queryKey: ["data-lab-history", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<DataLabHistoryResponse>(`/api/workspaces/${workspaceId}/data-lab/history`),
  });
  const history = historyQuery.data || {};
  const processing = listOf(history.processing);
  const models = listOf(history.models);
  const optimization = listOf(history.optimization);
  const agentSessions = listOf(history.agent_sessions);
  const recentItems = useMemo<RecentItem[]>(() => [
    ...processing.map((item) => ({ ...item, bucket: "Processing" })),
    ...models.map((item) => ({ ...item, bucket: "Model" })),
    ...optimization.map((item) => ({ ...item, bucket: "Optimization" })),
    ...agentSessions.map((item) => ({ ...item, bucket: "Agent" })),
  ].sort((left, right) => timestampOf(right) - timestampOf(left)).slice(0, 3), [agentSessions, models, optimization, processing]);

  return (
    <div className="data-lab-hub-page" aria-label="Data Lab hub">
      <section className="ops-surface ops-surface-emphasis">
        <div className="ops-surface-header">
          <div>
            <p className="eyebrow">Workspace Data Lab</p>
            <h1>Data Lab</h1>
            <p className="muted">
              Legacy Data Lab is the current full workbench. SPA Data Lab Agent is the agentic analysis runtime.
              Trusted execution is separate and should remain disabled unless authorized.
            </p>
          </div>
          <FlaskConical aria-hidden="true" />
        </div>
      </section>

      <section className="data-lab-route-grid" aria-label="Data Lab routes">
        {routeCards.map((card) => (
          <a key={card.title} className="data-lab-route-card" href={card.href}>
            <span className="data-lab-route-icon">{card.icon}</span>
            <span className="overview-card-label">{card.label}</span>
            <strong>{card.title}</strong>
            <span>{card.description}</span>
          </a>
        ))}
      </section>

      <section className="ops-surface">
        <div className="ops-surface-header">
          <div>
            <p className="eyebrow">Workspace History</p>
            <h2>Recent Data Lab activity</h2>
          </div>
          <Clock3 aria-hidden="true" />
        </div>
        <HistorySummary
          agentSessions={agentSessions.length}
          error={historyQuery.error}
          isError={historyQuery.isError}
          isLoading={historyQuery.isLoading}
          models={models.length}
          optimization={optimization.length}
          processing={processing.length}
          recentItems={recentItems}
          workspaceId={workspaceId}
        />
      </section>
    </div>
  );
}

function HistorySummary({
  agentSessions,
  error,
  isError,
  isLoading,
  models,
  optimization,
  processing,
  recentItems,
  workspaceId,
}: {
  agentSessions: number;
  error: unknown;
  isError: boolean;
  isLoading: boolean;
  models: number;
  optimization: number;
  processing: number;
  recentItems: RecentItem[];
  workspaceId: string;
}): JSX.Element {
  if (!workspaceId) {
    return (
      <InlineEmptyState
        title="No workspace selected"
        description="Select a workspace from /workspace or sign in again from /#auth-panel before loading Data Lab history."
      />
    );
  }

  if (isLoading) {
    return <LoadingState title="Loading Data Lab history" description="Fetching recent processing and model activity." />;
  }

  if (isError) {
    return (
      <InlineErrorState
        title="Data Lab history unavailable"
        description={summarizeError(error)}
      />
    );
  }

  return (
    <div className="data-lab-history-summary">
      <div className="data-lab-count-grid" aria-label="Data Lab history counts">
        <HistoryCount label="Processing" value={processing} />
        <HistoryCount label="Models" value={models} />
        <HistoryCount label="Optimization" value={optimization} />
        <HistoryCount label="Agent Sessions" value={agentSessions} />
      </div>
      {recentItems.length ? (
        <div className="data-lab-recent-list" aria-label="Recent Data Lab items">
          {recentItems.map((item, index) => (
            <article className="data-lab-recent-item" key={`${item.bucket}-${item.id || item.run_id || index}`}>
              <span className="overview-card-label">{item.bucket}</span>
              <strong>{item.title || item.run_id || item.id || "Untitled result"}</strong>
              <span>{item.status || "unknown"}</span>
              {item.summary ? <p className="muted">{item.summary}</p> : null}
            </article>
          ))}
        </div>
      ) : (
        <InlineEmptyState title="No Data Lab history yet" description="Run a legacy Data Lab workflow or Data Lab Agent session to populate this summary." />
      )}
    </div>
  );
}

function HistoryCount({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <div className="overview-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
