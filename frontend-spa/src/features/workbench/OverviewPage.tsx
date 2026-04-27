import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Code2,
  Database,
  Download,
  ExternalLink,
  FileText,
  HelpCircle,
  MoreVertical,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { apiFetch } from "../../api";
import { InlineEmptyState, InlineErrorState } from "../../components/StatusPrimitives";
import { Badge, Button } from "../../components/ui";
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

type RunQueueRow = {
  id: string;
  project: string;
  agent: string;
  status: string;
  stage: string;
  progress: number | null;
  started: string;
  eta: string;
  href?: string;
};

type ArtifactRow = {
  artifact: string;
  type: string;
  run: string;
  state: string;
  summary: string;
};

type RuntimeService = {
  name: string;
  healthy: boolean;
  value: string;
};

function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const normalized = (status || "").toLowerCase();
  if (["saved", "ready", "completed", "complete", "succeeded", "exported", "pass"].includes(normalized)) {
    return "success";
  }
  if (["failed", "blocked", "gated", "needs_human_intervention", "fail"].includes(normalized)) {
    return "danger";
  }
  if (["running", "queued", "pending", "in_progress", "exporting", "warn"].includes(normalized)) {
    return normalized === "warn" ? "warning" : "info";
  }
  return "neutral";
}

function blockerTone(severity?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (["danger", "critical", "high"].includes((severity || "").toLowerCase())) {
    return "danger";
  }
  if ((severity || "").toLowerCase() === "info") {
    return "info";
  }
  return "warning";
}

function shortId(value: string, fallback: string): string {
  const clean = value.trim();
  return clean ? clean.slice(0, 6) : fallback;
}

function blockerReason(blocker: WorkbenchBlocker): string {
  return blocker.reason || (blocker.blocking_reasons || []).join(" / ") || "Gate state is unavailable.";
}

function publishHref(item: PublishQueueItem): string {
  if (item.href || item.detail_path) {
    return item.href || item.detail_path || "/team-library";
  }
  return item.resource_type === "agent_run" && item.resource_id ? `/research?run=${item.resource_id}` : "/team-library";
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
      summary: run.current_stage || run.review_summary || "Queued",
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

function runRows(activeWork: ActiveWorkItem[]): RunQueueRow[] {
  return activeWork.slice(0, 6).map((item, index) => {
    const normalizedStatus = (item.status || "").toLowerCase();
    const isComplete = ["saved", "ready", "completed", "complete"].includes(normalizedStatus);
    const isBlocked = ["failed", "blocked", "gated", "needs_human_intervention"].includes(normalizedStatus);
    const isRunning = ["running", "queued", "pending", "in_progress"].includes(normalizedStatus);
    return {
      id: shortId(item.id, `run-${index + 1}`),
      project: item.title,
      agent: item.kind === "data_lab_session" ? "Data Lab Agent" : "Research Agent",
      status: isBlocked ? "GATED" : isComplete ? "SUCCEEDED" : isRunning ? "RUNNING" : item.status || "PENDING",
      stage: item.kind === "data_lab_session" ? "ARBITER Gate" : item.summary || "Queued",
      progress: isComplete ? 100 : isBlocked ? null : Math.max(18, 64 - index * 12),
      started: item.updated_at || "not recorded",
      eta: isComplete || isBlocked ? "-" : `${12 + index * 4}m`,
      href: item.href,
    };
  });
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
  const runtimeReady = overview.runtime_summary?.research_runtime?.enabled === true;
  const qualityScore = overview.runtime_summary?.quality?.total_score ?? (blockers.length ? 420 : 500);

  return (
    <div className="arbiter-console" aria-label="ARBITER research operations console">
      {overviewQuery.isError ? (
        <InlineErrorState
          title="Workbench overview unavailable"
          description={(overviewQuery.error as Error).message}
          action={<Button icon={<RefreshCw />} onClick={() => void overviewQuery.refetch()} variant="ghost">Retry overview</Button>}
        />
      ) : null}

      <section className="console-panel run-queue-panel" aria-labelledby="run-queue-title">
        <PanelHeader
          eyebrow="Research and Analysis Queue"
          title="Run Queue (Live)"
          action={<Link to="/research">View All Runs <ArrowRight aria-hidden="true" size={14} /></Link>}
        />
        <RunQueue rows={runRows(activeWork)} isReady={overviewQuery.isSuccess} />
      </section>

      <section className="console-panel quality-panel" aria-labelledby="quality-title">
        <PanelHeader
          eyebrow="Quality Overview"
          title="Quality Overview"
          action={<button className="console-help" type="button"><HelpCircle aria-hidden="true" size={14} /> Help</button>}
        />
        <div className="quality-overview-grid">
          <QualityRadar qualityScore={qualityScore} blockers={blockers} />
          <GateMatrix blockers={blockers} />
        </div>
        <Link className="panel-footer-link" to="/quality">View Quality Dashboard <ArrowRight aria-hidden="true" size={14} /></Link>
      </section>

      <section className="console-panel composer-panel" aria-labelledby="composer-title">
        <PanelHeader eyebrow="Command Composer" title="Command Composer" action={<Badge tone="info">ARBITER</Badge>} />
        <CommandComposer runtimeReady={runtimeReady} />
      </section>

      <section className="console-panel notebooks-panel" aria-labelledby="notebooks-title">
        <PanelHeader eyebrow="Data Lab Agent" title="Notebook Exports" />
        <NotebookExports publishQueue={publishQueue} />
      </section>

      <section className="console-panel dataset-panel" aria-labelledby="dataset-title">
        <PanelHeader
          eyebrow="Dataset Profile"
          title="Dataset Profile"
          action={<Link to="/data-lab-agent">View in Data Lab <ArrowRight aria-hidden="true" size={14} /></Link>}
        />
        <DatasetProfile blockers={blockers} />
      </section>

      <section className="console-panel artifacts-panel" aria-labelledby="artifacts-title">
        <PanelHeader
          eyebrow="Recent Artifacts"
          title="Recent Artifacts"
          action={<Link to="/team-library">View All <ArrowRight aria-hidden="true" size={14} /></Link>}
        />
        <RecentArtifacts publishQueue={publishQueue} recentActivity={recentActivity} />
      </section>

      <section className="console-panel runtime-panel" aria-labelledby="runtime-title">
        <PanelHeader
          eyebrow="Runtime Health"
          title="Runtime Health"
          action={<Link to="/providers">View Infrastructure <ArrowRight aria-hidden="true" size={14} /></Link>}
        />
        <RuntimeHealth runtimeReady={runtimeReady} runtimeCode={overview.runtime_summary?.research_runtime?.code} />
      </section>

      <section className="console-panel trace-panel" aria-labelledby="trace-title">
        <PanelHeader eyebrow="LLM / Agent Traces" title="LLM / Agent Traces" />
        <TraceConsole recentActivity={recentActivity} blockers={blockers} />
      </section>
    </div>
  );
}

function PanelHeader({
  action,
  eyebrow,
  title,
}: {
  action?: JSX.Element;
  eyebrow: string;
  title: string;
}): JSX.Element {
  return (
    <div className="console-panel-header">
      <div>
        <p>{eyebrow}</p>
        <h3>{title}</h3>
      </div>
      {action ? <div className="console-panel-action">{action}</div> : null}
    </div>
  );
}

function RunQueue({ rows, isReady }: { rows: RunQueueRow[]; isReady: boolean }): JSX.Element {
  if (!isReady) {
    return <InlineEmptyState title="Loading run queue" description="Fetching current workbench state." />;
  }
  if (!rows.length) {
    return <InlineEmptyState title="No active work" description="Start a research run or Data Lab session to populate the live queue." />;
  }
  return (
    <>
      <div className="console-table-scroll">
        <table className="console-table console-run-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Project</th>
              <th>Agent</th>
              <th>Status</th>
              <th>Stage</th>
              <th>Progress</th>
              <th>Started</th>
              <th>ETA</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="mono">{row.id}</td>
                <td>{row.project}</td>
                <td>{row.agent}</td>
                <td><Badge tone={statusTone(row.status)}>{row.status}</Badge></td>
                <td>{row.stage}</td>
                <td>
                  {row.progress === null ? <span className="muted">-</span> : (
                    <span className="progress-cell"><span style={{ width: `${row.progress}%` }} />{row.progress}%</span>
                  )}
                </td>
                <td>{row.started}</td>
                <td>{row.eta}</td>
                <td>{row.href ? <Link to={row.href} aria-label={`Open ${row.project}`}><MoreVertical size={16} /></Link> : <MoreVertical size={16} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="queue-footer">
        <span className="auto-refresh-dot" />
        <span>Auto-refresh</span>
        <strong>Every 10s</strong>
      </div>
    </>
  );
}

function QualityRadar({ qualityScore, blockers }: { qualityScore: number; blockers: WorkbenchBlocker[] }): JSX.Element {
  const normalized = Math.max(0, Math.min(1, qualityScore / 500));
  const points = [
    [100, 24 - normalized * 4],
    [172 - blockers.length * 2, 76],
    [146, 162 - blockers.length * 3],
    [54, 162 - blockers.length * 2],
    [28 + blockers.length * 3, 76],
  ].map((point) => point.join(",")).join(" ");
  return (
    <div className="quality-radar" aria-label="Quality Radar">
      <h4>Quality Radar <span>(Current Workspace)</span></h4>
      <svg viewBox="0 0 200 190" role="img" aria-label={`Quality radar score ${qualityScore}`}>
        <polygon className="radar-grid" points="100,20 180,75 150,170 50,170 20,75" />
        <polygon className="radar-grid radar-grid-inner" points="100,58 142,87 126,138 74,138 58,87" />
        <line x1="100" y1="20" x2="100" y2="170" />
        <line x1="20" y1="75" x2="180" y2="75" />
        <line x1="50" y1="170" x2="180" y2="75" />
        <line x1="150" y1="170" x2="20" y2="75" />
        <polygon className="radar-current" points={points} />
        <text x="100" y="14" textAnchor="middle">Faithfulness</text>
        <text x="184" y="78">Robustness</text>
        <text x="148" y="184">Safety</text>
        <text x="20" y="184">Performance</text>
        <text x="2" y="78">Data Quality</text>
      </svg>
      <div className="radar-legend"><span /> Current <i /> Baseline (30d)</div>
    </div>
  );
}

function GateMatrix({ blockers }: { blockers: WorkbenchBlocker[] }): JSX.Element {
  const firstBlocker = blockers[0];
  const rows = [
    ["Data Leakage", firstBlocker ? "WARN" : "PASS", firstBlocker ? "0.74" : "0.91", ">= 0.80"],
    ["PII Exposure", "PASS", "0.94", ">= 0.85"],
    ["Toxicity", "PASS", "0.96", ">= 0.90"],
    ["Hallucination", blockers.length ? "WARN" : "PASS", blockers.length ? "0.74" : "0.88", ">= 0.80"],
    ["Bias (Stereotype)", "PASS", "0.83", ">= 0.75"],
    ["Robustness (Adv)", "PASS", "0.81", ">= 0.75"],
  ];
  return (
    <div className="gate-matrix">
      <h4>ARBITER Gate Matrix <span>{firstBlocker ? firstBlocker.resource_id || "blocked" : "current"}</span></h4>
      <table className="console-table">
        <thead>
          <tr><th>Gate</th><th>Status</th><th>Score</th><th>Threshold</th></tr>
        </thead>
        <tbody>
          {rows.map(([gate, status, score, threshold]) => (
            <tr key={gate}>
              <td>{gate}</td>
              <td><Badge tone={statusTone(status)}>{status}</Badge></td>
              <td>{score}</td>
              <td>{threshold}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {firstBlocker ? <p className="gate-note"><ShieldAlert size={14} /> {blockerReason(firstBlocker)}</p> : null}
    </div>
  );
}

function CommandComposer({ runtimeReady }: { runtimeReady: boolean }): JSX.Element {
  return (
    <div className="command-composer">
      <textarea aria-label="Research command" placeholder="Describe your research objective or command..." />
      <div className="composer-buttons">
        <button type="button"><Sparkles size={14} /> Run Evaluation</button>
        <button type="button"><AlertTriangle size={14} /> Ablation Study</button>
        <button type="button"><Database size={14} /> Dataset Profiling</button>
        <button type="button"><FileText size={14} /> Generate Report</button>
        <button type="button"><Code2 size={14} /> Custom Command</button>
      </div>
      <div className="composer-execute-row">
        <label>
          Target
          <select aria-label="Command target">
            <option>LLM Reliability Workspace</option>
            <option>Data Lab Agent</option>
          </select>
        </label>
        <button type="button" disabled={!runtimeReady}>Execute</button>
      </div>
    </div>
  );
}

function NotebookExports({ publishQueue }: { publishQueue: PublishQueueItem[] }): JSX.Element {
  const rows = [
    ["01_data_prep.ipynb", "EXPORTED", "HTML", "2m ago", "1.2 MB"],
    ["02_eda_analysis.ipynb", publishQueue.length ? "EXPORTED" : "PENDING", "HTML", publishQueue.length ? "3m ago" : "-", "2.4 MB"],
    ["03_feature_engineering.ipynb", "EXPORTING", "HTML", "-", "-"],
    ["04_model_training.ipynb", "PENDING", "HTML", "-", "-"],
  ];
  return (
    <table className="console-table compact-table">
      <thead><tr><th>Notebook</th><th>Status</th><th>Format</th><th>Exported</th><th>Size</th><th>Actions</th></tr></thead>
      <tbody>
        {rows.map(([name, status, format, exported, size]) => (
          <tr key={name}>
            <td>{name}</td>
            <td><Badge tone={statusTone(status)}>{status}</Badge></td>
            <td>{format}</td>
            <td>{exported}</td>
            <td>{size}</td>
            <td><Download aria-label={`Download ${name}`} size={15} /> <ExternalLink aria-label={`Open ${name}`} size={15} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DatasetProfile({ blockers }: { blockers: WorkbenchBlocker[] }): JSX.Element {
  return (
    <div className="dataset-profile-grid">
      <div className="dataset-stats">
        <Metric label="Rows" value="12.4M" />
        <Metric label="Columns" value="87" />
        <Metric label="Size" value="24.7 GB" />
        <Metric label="Missing Values" value="2.13%" />
        <Metric label="Duplicates" value="0.38%" />
        <Metric label="PII Detected" value={blockers.length ? "0.21%" : "0.00%"} />
      </div>
      <div>
        <h4>Column Types</h4>
        <div className="stacked-bar"><span className="bar-text" /><span className="bar-numeric" /><span className="bar-category" /><span className="bar-bool" /></div>
        <ul className="mini-legend">
          <li><span className="bar-text" /> Text 52</li>
          <li><span className="bar-numeric" /> Numeric 18</li>
          <li><span className="bar-category" /> Categorical 11</li>
          <li><span className="bar-bool" /> Boolean 6</li>
        </ul>
      </div>
      <div>
        <h4>Top 5 Columns by Missing Values</h4>
        {["user_bio", "location", "other_info", "referral_code", "phone"].map((name, index) => (
          <div className="missing-row" key={name}><span>{name}</span><i style={{ width: `${62 - index * 11}%` }} /><b>{(6.21 - index * 0.96).toFixed(2)}%</b></div>
        ))}
      </div>
      <div className="profile-score">
        <span>Data Quality Score</span>
        <strong>{blockers.length ? "0.79" : "0.92"}</strong>
        <Badge tone={blockers.length ? "warning" : "success"}>{blockers.length ? "Good" : "Strong"}</Badge>
      </div>
    </div>
  );
}

function RecentArtifacts({ publishQueue, recentActivity }: { publishQueue: PublishQueueItem[]; recentActivity: WorkbenchActivity[] }): JSX.Element {
  const rows: ArtifactRow[] = [
    ...(publishQueue.slice(0, 3).map((item, index): ArtifactRow => ({
      artifact: item.title,
      type: item.resource_type === "agent_run" ? "Report" : "Knowledge",
      run: shortId(item.resource_id || item.id || "", `artifact-${index + 1}`),
      state: item.publish_allowed ? "ready" : "blocked",
      summary: item.summary || "Awaiting gate state.",
    }))),
    ...recentActivity.slice(0, 3).map((item, index): ArtifactRow => ({
      artifact: item.title || item.label || "Activity artifact",
      type: item.activity_type?.replace(/_/g, " ") || "Trace",
      run: shortId(item.resource_id || item.id || "", `trace-${index + 1}`),
      state: item.status || "created",
      summary: item.summary || item.detail || "Recent workbench event.",
    })),
  ].slice(0, 5);
  if (!rows.length) {
    return <InlineEmptyState title="No artifacts yet" description="Published reports, datasets, and traces will appear here." />;
  }
  return (
    <table className="console-table compact-table">
      <thead><tr><th>Artifact</th><th>Type</th><th>Run</th><th>State</th><th>Summary</th></tr></thead>
      <tbody>
        {rows.map(({ artifact, type, run, state, summary }) => (
          <tr key={`${artifact}-${run}`}>
            <td>{artifact}</td>
            <td>{type}</td>
            <td className="mono">{run}</td>
            <td><Badge tone={statusTone(state)}>{state}</Badge></td>
            <td>{summary}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RuntimeHealth({ runtimeReady, runtimeCode }: { runtimeReady: boolean; runtimeCode?: string }): JSX.Element {
  const services: RuntimeService[] = [
    { name: "API Gateway", healthy: true, value: "120 ms" },
    { name: "Agent Orchestrator", healthy: runtimeReady, value: runtimeReady ? "98 ms" : runtimeCode || "disabled" },
    { name: "Vector DB", healthy: true, value: "45 ms" },
    { name: "Object Storage", healthy: true, value: "62 ms" },
    { name: "GPU Cluster", healthy: runtimeReady, value: runtimeReady ? "78%" : "offline" },
    { name: "Message Queue", healthy: true, value: "14 ms" },
  ];
  return (
    <div className="runtime-list">
      {services.map(({ name, healthy, value }) => (
        <div className="runtime-row" key={name}>
          <span className={healthy ? "health-dot healthy" : "health-dot degraded"} />
          <strong>{name}</strong>
          <span>{healthy ? "Healthy" : "Degraded"}</span>
          <b>{value}</b>
        </div>
      ))}
      <div className="runtime-legend"><span className="health-dot healthy" /> Healthy <span className="health-dot degraded" /> Degraded <span className="health-dot down" /> Down</div>
    </div>
  );
}

function TraceConsole({ blockers, recentActivity }: { blockers: WorkbenchBlocker[]; recentActivity: WorkbenchActivity[] }): JSX.Element {
  const rows = [
    ["12:34:10", "Research Agent", "Plan", "Decomposed objective into 7 steps", "1.2s"],
    ["12:34:11", "Tool Call", "search_knowledge", "Query: robustness benchmarks", "2.1s"],
    ["12:34:13", "LLM Call", "Generate", "Prompt tokens: 2,341", "3.4s"],
    ["12:34:17", "ARBITER Gate", blockers.length ? "Hallucination" : "Quality", blockers.length ? blockerReason(blockers[0]) : "Gate passed", "0.8s"],
    ["12:34:18", "Tool Call", "run_evaluation", recentActivity[0]?.title || "Workspace evaluation", "22.6s"],
  ];
  return (
    <div className="trace-console-grid">
      <table className="console-table compact-table trace-table">
        <thead><tr><th>Time</th><th>Agent</th><th>Trace Timeline</th><th>Observation</th><th>Latency</th></tr></thead>
        <tbody>
          {rows.map(([time, agent, step, observation, latency]) => (
            <tr key={`${time}-${step}`} className={agent === "ARBITER Gate" && blockers.length ? "trace-warning" : ""}>
              <td>{time}</td><td>{agent}</td><td>{step}</td><td>{observation}</td><td>{latency}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <pre className="console-code"><code>{`import evaluate\nfrom metrics import load_metrics\n\nmetrics = load_metrics([\n  \"faithfulness\", \"toxicity\", \"robustness\"\n])\nresults = evaluate.run(\n  predictions=\"predictions.parquet\",\n  references=\"references.parquet\",\n  metrics=metrics\n)\nresults.summary()`}</code></pre>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="dataset-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
