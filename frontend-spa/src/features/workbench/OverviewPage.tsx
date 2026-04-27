import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Clock3, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { apiFetch } from "../../api";
import { InlineEmptyState, InlineErrorState } from "../../components/StatusPrimitives";
import { Badge, Button, MetricPill } from "../../components/ui";
import { endpoints } from "../../shared/api/endpoints";
import { queryKeys } from "../../shared/queryKeys";
import type {
  ActiveWorkItem,
  PublishQueueItem,
  WorkbenchActivity,
  WorkbenchBlocker,
  WorkbenchOverview,
} from "./types";

type UseAppState = () => {
  workspaceId: string;
};

function blockerTone(severity?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (severity === "danger" || severity === "critical") {
    return "danger";
  }
  if (severity === "info") {
    return "info";
  }
  return "warning";
}

function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const normalized = (status || "").toLowerCase();
  if (["saved", "ready", "completed", "complete"].includes(normalized)) {
    return "success";
  }
  if (["failed", "blocked", "needs_human_intervention"].includes(normalized)) {
    return "danger";
  }
  if (["running", "queued", "pending", "in_progress"].includes(normalized)) {
    return "info";
  }
  return "neutral";
}

function displayDate(value?: string): string {
  return value || "not recorded";
}

function overviewActiveWork(overview?: WorkbenchOverview): ActiveWorkItem[] {
  const explicit = overview?.active_work || [];
  const runs = explicit.length
    ? explicit
    : (overview?.active_runs || []).map((run) => ({
      id: run.id,
      kind: "research_run",
      title: run.topic || run.title || "Research run",
      status: run.queue_status || run.status || run.current_stage || "unknown",
      summary: run.review_summary || run.question || "No summary recorded.",
      href: run.detail_path || `/research?run=${run.id}`,
      updated_at: run.updated_at || run.finished_at || run.started_at,
      blocker_count: run.blocking_reasons?.length || 0,
    }));

  const sessions = (overview?.data_lab_sessions || []).map((session) => {
    const id = session.run_id || session.id || "";
    return {
      id,
      kind: "data_lab_session",
      title: session.title || "Data Lab session",
      status: session.run_status || session.status || "unknown",
      summary: session.summary || "No summary recorded.",
      href: session.detail_path || (id ? `/data-lab-agent?run=${id}` : "/data-lab-agent"),
      updated_at: session.updated_at || session.finished_at || session.created_at,
      blocker_count: 0,
    };
  });

  return [...runs, ...sessions].sort((left, right) => (right.updated_at || "").localeCompare(left.updated_at || ""));
}

function blockerKey(blocker: WorkbenchBlocker, index: number): string {
  return blocker.id || `${blocker.resource_type || "blocker"}-${blocker.resource_id || index}`;
}

function blockerReason(blocker: WorkbenchBlocker): string {
  return blocker.reason || (blocker.blocking_reasons || []).join(" / ") || "Gate state is unavailable.";
}

function blockerSource(blocker: WorkbenchBlocker): string {
  return blocker.source || blocker.resource_type || "quality";
}

function publishKey(item: PublishQueueItem, index: number): string {
  return item.id || `${item.resource_type || "publish"}-${item.resource_id || index}`;
}

function publishHref(item: PublishQueueItem): string {
  if (item.href || item.detail_path) {
    return item.href || item.detail_path || "/team-library";
  }
  return item.resource_type === "agent_run" && item.resource_id ? `/research?run=${item.resource_id}` : "/team-library";
}

function activityKey(item: WorkbenchActivity, index: number): string {
  return item.id || `${item.activity_type || "activity"}-${item.resource_id || index}`;
}

function activityLabel(item: WorkbenchActivity): string {
  return item.label || item.title || item.activity_type?.replace(/_/g, " ") || "Activity";
}

function activityDetail(item: WorkbenchActivity): string {
  return item.detail || item.summary || item.at || item.occurred_at || "No detail recorded.";
}

export function OverviewPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();
  const overviewQuery = useQuery({
    queryKey: queryKeys.workbenchOverview(workspaceId),
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<WorkbenchOverview>(endpoints.workbenchOverview(workspaceId)),
  });
  const overview = overviewQuery.data || {};
  const activeWork = overviewActiveWork(overview);
  const blockers = overview.quality_blockers || [];
  const publishQueue = overview.publish_queue || [];
  const recentActivity = overview.recent_activity || [];
  const researchRuntime = overview.runtime_summary?.research_runtime;
  const runtimeReady = researchRuntime?.enabled === true;

  return (
    <div className="terminal-page overview-terminal">
      <section className="decision-strip" aria-label="Workbench decision summary">
        <MetricPill label="Active Work" value={overviewQuery.isSuccess ? activeWork.length : overviewQuery.isLoading ? "Loading" : "Unknown"} />
        <MetricPill label="Quality Blockers" tone={blockers.length ? "warning" : overviewQuery.isError ? "danger" : "success"} value={overviewQuery.isSuccess ? blockers.length : overviewQuery.isError ? "UNKNOWN" : "-"} />
        <MetricPill label="Publish Queue" value={overviewQuery.isSuccess ? publishQueue.length : "-"} />
        <MetricPill label="Research Runtime" tone={runtimeReady ? "success" : "warning"} value={overviewQuery.isSuccess ? runtimeReady ? "Ready" : "Disabled" : "Unknown"} />
      </section>

      <section className="terminal-panel terminal-panel-main">
        <div className="terminal-panel-header">
          <div>
            <p className="eyebrow">Active Work</p>
            <h3>Research and Analysis Queue</h3>
          </div>
          <Link className="terminal-link" to="/research">Open Research <ArrowRight aria-hidden="true" size={15} /></Link>
        </div>
        {overviewQuery.isError ? (
          <InlineErrorState
            title="Workbench overview unavailable"
            description={(overviewQuery.error as Error).message}
            action={<Button icon={<RefreshCw />} onClick={() => void overviewQuery.refetch()} variant="ghost">Retry overview</Button>}
          />
        ) : null}
        {!overviewQuery.isError && overviewQuery.isSuccess && !activeWork.length ? (
          <InlineEmptyState title="No active work" description="Start a research run or Data Lab session to populate the workbench." />
        ) : null}
        {activeWork.length ? <ActiveWorkTable items={activeWork} /> : null}
      </section>

      <aside className="terminal-panel terminal-inspector">
        <div className="terminal-panel-header">
          <div>
            <p className="eyebrow">Governance</p>
            <h3>Quality Blockers</h3>
          </div>
          <Link className="terminal-link" to="/quality">Quality <ArrowRight aria-hidden="true" size={15} /></Link>
        </div>
        <BlockerList blockers={blockers} isReady={overviewQuery.isSuccess} />
      </aside>

      <section className="terminal-panel">
        <div className="terminal-panel-header">
          <div>
            <p className="eyebrow">Publication</p>
            <h3>Publish-ready Queue</h3>
          </div>
          <Link className="terminal-link" to="/team-library">Library <ArrowRight aria-hidden="true" size={15} /></Link>
        </div>
        <PublishQueue items={publishQueue} isReady={overviewQuery.isSuccess} />
      </section>

      <section className="terminal-panel terminal-panel-span">
        <div className="terminal-panel-header">
          <div>
            <p className="eyebrow">Recent Activity</p>
            <h3>Operational Timeline</h3>
          </div>
          <Badge tone={runtimeReady ? "success" : "warning"}>{researchRuntime?.code || (runtimeReady ? "runtime_ready" : "runtime_unknown")}</Badge>
        </div>
        <ActivityTimeline items={recentActivity} isReady={overviewQuery.isSuccess} />
      </section>
    </div>
  );
}

function ActiveWorkTable({ items }: { items: ActiveWorkItem[] }): JSX.Element {
  return (
    <div className="terminal-table-scroll">
      <table className="terminal-table">
        <thead>
          <tr>
            <th scope="col">Work</th>
            <th scope="col">Kind</th>
            <th scope="col">Status</th>
            <th scope="col">Updated</th>
            <th scope="col">Open</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.kind}-${item.id}`}>
              <td>
                <strong>{item.title}</strong>
                <span>{item.summary || "No summary recorded."}</span>
              </td>
              <td>{item.kind.replace(/_/g, " ")}</td>
              <td><Badge tone={statusTone(item.status)}>{item.status || "unknown"}</Badge></td>
              <td>{displayDate(item.updated_at)}</td>
              <td>{item.href ? <Link to={item.href}>Open</Link> : <span className="muted">No link</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BlockerList({ blockers, isReady }: { blockers: WorkbenchBlocker[]; isReady: boolean }): JSX.Element {
  if (!isReady) {
    return <InlineEmptyState title="Blockers unknown" description="The workbench fails closed until overview data is available." />;
  }
  if (!blockers.length) {
    return <InlineEmptyState title="No quality blockers" description="No workspace blockers were reported by the overview service." />;
  }
  return (
    <div className="terminal-record-list">
      {blockers.map((blocker, index) => (
        <article className="terminal-record terminal-record-warning" key={blockerKey(blocker, index)}>
          <div>
            <strong>{blocker.title || blocker.resource_type || "Quality blocker"}</strong>
            <span>{blockerReason(blocker)}</span>
          </div>
          <Badge tone={blockerTone(blocker.severity)}>{blockerSource(blocker)}</Badge>
        </article>
      ))}
    </div>
  );
}

function PublishQueue({ items, isReady }: { items: PublishQueueItem[]; isReady: boolean }): JSX.Element {
  if (!isReady) {
    return <InlineEmptyState title="Publication state unknown" description="Publish actions remain blocked until gate state is current." />;
  }
  if (!items.length) {
    return <InlineEmptyState title="Nothing ready to publish" description="Reviewed records appear here after delivery gates pass." />;
  }
  return (
    <div className="terminal-record-list">
      {items.map((item, index) => (
        <article className="terminal-record" key={publishKey(item, index)}>
          <div>
            <strong>{item.title}</strong>
            <span>{item.target || item.summary || (item.blocking_reasons || []).join(" / ") || "No target recorded."}</span>
          </div>
          <Link to={publishHref(item)}>Open</Link>
          <Badge tone={item.publish_allowed === false ? "warning" : statusTone(item.status)}>
            {item.publish_allowed === false ? "blocked" : item.status || "ready"}
          </Badge>
        </article>
      ))}
    </div>
  );
}

function ActivityTimeline({ items, isReady }: { items: WorkbenchActivity[]; isReady: boolean }): JSX.Element {
  if (!isReady) {
    return <InlineEmptyState title="Activity unknown" description="Recent events will load after the overview service responds." />;
  }
  if (!items.length) {
    return <InlineEmptyState title="No recent activity" description="Research, Data Lab, Quality, and Library events will appear here." />;
  }
  return (
    <div className="terminal-timeline">
      {items.map((item, index) => (
        <article className="terminal-timeline-item" key={activityKey(item, index)}>
          <Clock3 aria-hidden="true" size={16} />
          <div>
            <strong>{activityLabel(item)}</strong>
            <span>{activityDetail(item)}</span>
          </div>
          {item.href || item.detail_path ? <Link to={item.href || item.detail_path || ""}>Open</Link> : <AlertTriangle aria-hidden="true" size={15} />}
        </article>
      ))}
    </div>
  );
}
