import { Bot, Clock3, Database, FlaskConical, History, PlaySquare, Settings2, Table2 } from "lucide-react";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api";
import { InlineEmptyState, InlineErrorState, LoadingState } from "../components/StatusPrimitives";
import { ActionLink, Badge, Card, MetricCard, PageHeader, Surface } from "../components/ui";

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

type WorkflowStep = {
  description: string;
  href: string;
  label: "Legacy workbench" | "SPA runtime";
  title: string;
  icon: JSX.Element;
};

type RecentItem = HistoryItem & {
  bucket: string;
};

const workflowSteps: WorkflowStep[] = [
  {
    description: "Upload and inspect structured CSV, XLSX, XLS, or JSON datasets.",
    href: "/data-lab",
    icon: <Database aria-hidden="true" />,
    label: "Legacy workbench",
    title: "Dataset",
  },
  {
    description: "Preview cleaning, transformations, and feature work before committing.",
    href: "/data-lab/preparation",
    icon: <Settings2 aria-hidden="true" />,
    label: "Legacy workbench",
    title: "Preparation",
  },
  {
    description: "Run preflight checks and execute existing statistical model workflows.",
    href: "/data-lab/model",
    icon: <FlaskConical aria-hidden="true" />,
    label: "Legacy workbench",
    title: "Model",
  },
  {
    description: "Review manifests, artifacts, warnings, and model output details.",
    href: "/data-lab/results",
    icon: <Table2 aria-hidden="true" />,
    label: "Legacy workbench",
    title: "Results",
  },
  {
    description: "Trace processing, model, optimization, and agent activity.",
    href: "/data-lab/history",
    icon: <History aria-hidden="true" />,
    label: "Legacy workbench",
    title: "History",
  },
  {
    description: "Continue from structured data into the agent-assisted analysis runtime.",
    href: "/app/data-lab-agent",
    icon: <Bot aria-hidden="true" />,
    label: "SPA runtime",
    title: "Agent",
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
    <div className="data-lab-hub-page data-lab-hub-redesign" aria-label="Data Lab hub">
      <Surface
        className="data-lab-hub-hero"
        title={(
          <PageHeader
            title="Data Lab"
            description="Prepare structured datasets, run model checks, review results, and continue with the agent runtime."
          />
        )}
        actions={(
          <ActionLink href="/data-lab/optimization" icon={<PlaySquare size={16} aria-hidden="true" />} variant="ghost">
            Optimization
          </ActionLink>
        )}
      >
        <p className="muted data-lab-hub-compat-note">
          Legacy Data Lab is the current full workbench. SPA Data Lab Agent is the agentic analysis runtime.
        </p>
        <div className="data-lab-workflow-strip" aria-label="Data Lab workflow">
          {workflowSteps.map((step, index) => (
            <a className="data-lab-workflow-step" href={step.href} key={step.title}>
              <span>{index + 1}</span>
              <strong>{step.title}</strong>
            </a>
          ))}
        </div>
      </Surface>

      <div className="data-lab-workbench-layout">
        <section className="data-lab-workflow-grid" aria-label="Data Lab workflow routes">
          {workflowSteps.map((step) => (
            <a
              key={step.title}
              aria-label={`${step.title === "Dataset" ? "Dataset Intake" : step.title} - ${step.label}`}
              className="data-lab-route-card data-lab-route-card-redesign"
              href={step.href}
            >
              <Card className="data-lab-route-card__body">
                <span className="data-lab-route-icon">{step.icon}</span>
                <Badge tone="neutral">{step.label}</Badge>
                <strong>{step.title}</strong>
                <span>{step.description}</span>
              </Card>
            </a>
          ))}
        </section>

        <aside className="data-lab-status-inspector" aria-label="Workspace history and safety">
          <Surface
            eyebrow="Workspace history"
            title="Recent activity"
            actions={<Clock3 aria-hidden="true" />}
          >
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
          </Surface>

          <Surface tone="warning" title="Execution boundary">
            <p className="muted">
              Trusted Python execution is separate and should remain disabled unless authorized.
            </p>
          </Surface>
        </aside>
      </div>
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
        <MetricCard label="Processing" value={processing} />
        <MetricCard label="Models" value={models} />
        <MetricCard label="Optimization" value={optimization} />
        <MetricCard label="Agent Sessions" value={agentSessions} />
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
