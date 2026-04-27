import { Badge, CodeBlock, JsonBlock, MetricPill, Surface } from "../ui";
import { compactList, displayStatus, statusTone } from "./helpers";
import type { AgentMessage, AgentSession } from "./types";

export function TracePanel({
  currentExecutorMode,
  currentSession,
  latestAssistant,
  reportMarkdown,
  sessionStatus,
}: {
  currentExecutorMode: string;
  currentSession?: AgentSession;
  latestAssistant?: AgentMessage;
  reportMarkdown: string;
  sessionStatus: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Trace Panel"
      title="Runtime Evidence"
      description="Session state, executor mode, LLM routing, safety events, notebook/report artifacts, and ARBITER state."
      actions={<Badge tone={statusTone(sessionStatus)}>{displayStatus(sessionStatus)}</Badge>}
    >
      <div className="metric-strip" aria-label="Runtime trace metrics">
        <MetricPill label="Executor" value={currentExecutorMode} tone={currentExecutorMode === "not run" ? "neutral" : "warning"} />
        <MetricPill label="LLM" value={currentSession?.llm?.ready ? "Configured" : "Fallback"} tone={currentSession?.llm?.ready ? "success" : "warning"} />
        <MetricPill label="Cells" value={currentSession?.cells?.length || 0} />
        <MetricPill label="Safety" value={currentSession?.safety_events?.length || 0} tone={currentSession?.safety_events?.length ? "warning" : "neutral"} />
      </div>
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>Session routing</strong>
          <Badge tone={statusTone(sessionStatus)}>{displayStatus(sessionStatus)}</Badge>
        </div>
        <p className="muted">
          Mode: {currentExecutorMode}. Strategy: {currentSession?.executor?.strategy || "unknown"}. IPython: {currentSession?.executor?.ipython_enabled ? "enabled" : "disabled or unknown"}.
        </p>
        <p className="muted">
          LLM: {currentSession?.llm?.ready ? `${currentSession.llm.source} ${currentSession.llm.coder_model}` : "rules fallback or unknown"}.
        </p>
        <p className="muted">
          ARBITER: {currentSession?.math?.mode || "off"}. Margin: {typeof currentSession?.math?.override_margin === "number" ? currentSession.math.override_margin.toFixed(2) : "-"}.
        </p>
      </div>
      {latestAssistant ? (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Latest assistant</strong>
            <Badge tone={statusTone(latestAssistant.status)}>{displayStatus(latestAssistant.status, "RECORDED")}</Badge>
          </div>
          <p>{latestAssistant.content}</p>
        </div>
      ) : null}
      {currentSession?.math?.v2_state_summary ? (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>ARBITER v2 state</strong>
            <Badge tone={statusTone(currentSession.math.v2_state_summary.run_status)}>{displayStatus(currentSession.math.v2_state_summary.run_status)}</Badge>
          </div>
          <p className="muted">
            successful cells {currentSession.math.v2_state_summary.successful_cell_count || 0} / safety events {currentSession.math.v2_state_summary.safety_event_count || 0}
          </p>
          <p className="muted">
            mode {currentSession.math.mode || "off"} / override margin {typeof currentSession.math.override_margin === "number" ? currentSession.math.override_margin.toFixed(2) : "-"} / successful cells {currentSession.math.v2_state_summary.successful_cell_count || 0} / safety events {currentSession.math.v2_state_summary.safety_event_count || 0} / run {currentSession.math.v2_state_summary.run_status || "unknown"}
          </p>
          <p className="muted">Recent failures: {compactList(currentSession.math.v2_state_summary.recent_failure_classes)}.</p>
          <details>
            <summary>Raw ARBITER state</summary>
            <JsonBlock value={currentSession.math.v2_state_summary} />
          </details>
        </div>
      ) : null}
      {currentSession?.safety_events?.length ? (
        <details className="list-card static-card">
          <summary>Safety events</summary>
          <JsonBlock value={currentSession.safety_events} />
        </details>
      ) : (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Safety events</strong>
            <Badge tone={currentSession ? "neutral" : "warning"}>{currentSession ? "NONE" : "UNKNOWN"}</Badge>
          </div>
          <p className="muted">{currentSession ? "No safety events recorded for this session." : "Select a session to inspect safety events."}</p>
        </div>
      )}
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>Report</strong>
          <Badge tone={reportMarkdown || currentSession?.report_path ? "success" : "neutral"}>{reportMarkdown || currentSession?.report_path ? "AVAILABLE" : "NOT GENERATED"}</Badge>
        </div>
        <p className="muted">{currentSession?.report_path ? `Artifact: ${currentSession.report_path}` : "Generate Report creates a markdown report for the selected session."}</p>
        {reportMarkdown ? <CodeBlock label="Generated Report">{reportMarkdown}</CodeBlock> : null}
      </div>
    </Surface>
  );
}
