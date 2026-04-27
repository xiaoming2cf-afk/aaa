import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, CodeBlock, JsonBlock, Surface } from "../ui";
import { displayStatus, formatBytes, formatFallbackReason, formatMaybeNumber, statusTone } from "./helpers";
import type { AgentMessage, AgentSession } from "./types";

function MessageTimelineItem({ item }: { item: AgentMessage }): JSX.Element {
  return (
    <article className="timeline-item">
      <span className="timeline-dot" aria-hidden="true" />
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>{item.role}</strong>
          <Badge tone={statusTone(item.status)}>{displayStatus(item.status, "RECORDED")}</Badge>
        </div>
        <p>{item.content}</p>
        <div className="inline-metrics">
          {item.coder_source ? <span>Coder: {item.coder_source}</span> : null}
          <span>Mode: {item.execution_mode || "not executed"}</span>
          {item.user_code ? <span>Manual code</span> : null}
          {item.profile_snapshot ? <span>Snapshot {item.profile_snapshot.rows || 0}x{item.profile_snapshot.columns || 0}</span> : null}
        </div>
        {item.human_intervention?.required ? (
          <div className="list-card static-card">
            <div className="list-card-title">
              <strong>Human intervention required</strong>
              <Badge tone="warning">ACTION</Badge>
            </div>
            <p className="muted">{item.human_intervention.reason || "Manual review is required before continuing."}</p>
            {item.human_intervention.next_action ? <p className="muted">{item.human_intervention.next_action}</p> : null}
          </div>
        ) : null}
        {item.human_intervention?.provided ? (
          <p className="muted">Manual note: {item.human_intervention.note || "Provided manually."}</p>
        ) : null}
        {item.code ? <CodeBlock label="Code">{item.code}</CodeBlock> : null}
        {item.execution?.stdout ? <CodeBlock label="stdout">{item.execution.stdout}</CodeBlock> : null}
        {item.execution?.stderr ? <CodeBlock label="stderr">{item.execution.stderr}</CodeBlock> : null}
        {item.execution?.error ? <CodeBlock label="error">{item.execution.error}</CodeBlock> : null}
        {item.risk_notes?.length ? (
          <div className="list-card static-card">
            <div className="list-card-title">
              <strong>Risk notes</strong>
              <Badge tone="warning">{item.risk_notes.length}</Badge>
            </div>
            <p className="muted">{item.risk_notes.join(" | ")}</p>
          </div>
        ) : null}
        {item.artifact_manifest?.count ? (
          <details>
            <summary>Artifacts</summary>
            <div className="inline-metrics">
              <span>{item.artifact_manifest.count} files</span>
              <span>{item.artifact_manifest.image_count || 0} images</span>
              <span>{formatBytes(item.artifact_manifest.total_size_bytes)}</span>
            </div>
            {item.execution?.artifacts?.length || item.artifact_manifest.names?.length ? (
              <ul>
                {(item.execution?.artifacts || []).map((artifact) => (
                  <li key={`${item.id}-${artifact.path}`}>{artifact.relative_path || artifact.name}</li>
                ))}
                {!item.execution?.artifacts?.length ? item.artifact_manifest.names?.map((name) => (
                  <li key={`${item.id}-${name}`}>{name}</li>
                )) : null}
              </ul>
            ) : null}
          </details>
        ) : null}
        {item.repair_trace?.length ? (
          <details>
            <summary>Repair trace</summary>
            <JsonBlock value={item.repair_trace} />
          </details>
        ) : null}
        {item.math_trace ? (
          <div className="list-card static-card">
            <div className="list-card-title">
              <strong>ARBITER trace</strong>
              <Badge tone={statusTone(item.math_trace.v2_state_summary?.run_status)}>{displayStatus(item.math_trace.v2_state_summary?.run_status)}</Badge>
            </div>
            <p className="muted">
              mode {item.math_trace.mode || "off"} / override margin {typeof item.math_trace.override_margin === "number" ? item.math_trace.override_margin.toFixed(2) : "-"}
            </p>
            {item.math_trace.retrieval?.v2?.comparison ? (
              <p className="muted">
                retrieval baseline {item.math_trace.retrieval.v2.comparison.baseline_choice || "none"} / proposed {item.math_trace.retrieval.v2.comparison.proposed_choice || "none"} / chosen {item.math_trace.retrieval.v2.comparison.chosen_choice || "none"} / fallback {formatFallbackReason(item.math_trace.retrieval.v2.comparison.fallback_reason)} / advantage {formatMaybeNumber(item.math_trace.retrieval.v2.comparison.advantage)}
              </p>
            ) : null}
            {item.math_trace.repair_decisions?.length ? (
              <div className="list-stack">
                {item.math_trace.repair_decisions.map((decision, index) => (
                  <p key={`${item.id}-repair-${index}`} className="muted">
                    repair {index + 1}: {decision.best_action || "unknown"} / {decision.error_class || "unknown"} / fallback {formatFallbackReason(decision.v2?.comparison?.fallback_reason)} / chosen {decision.v2?.comparison?.chosen_choice || decision.best_action || "unknown"}
                  </p>
                ))}
              </div>
            ) : null}
            <details>
              <summary>Raw ARBITER trace</summary>
              <JsonBlock value={item.math_trace} />
            </details>
          </div>
        ) : null}
        {item.knowledge_cards?.length ? (
          <details>
            <summary>Knowledge cards</summary>
            <div className="record-list">
              {item.knowledge_cards.map((card) => (
                <div key={`${item.id}-${card.id}`} className="list-card static-card">
                  <div className="list-card-title">
                    <strong>{card.title}</strong>
                    <Badge tone="info">{card.source_type}</Badge>
                  </div>
                  <p>{card.summary}</p>
                  {typeof card.score === "number" ? <p className="muted">Score: {card.score.toFixed(3)}</p> : null}
                </div>
              ))}
            </div>
          </details>
        ) : null}
        {item.llm_trace_summary?.length ? (
          <details>
            <summary>LLM trace summary</summary>
            <div className="record-list">
              {item.llm_trace_summary.map((trace, index) => (
                <div key={`${item.id}-llm-${index}`} className="list-card static-card">
                  <div className="list-card-title">
                    <strong>{trace.role}</strong>
                    <Badge tone={trace.llm_error ? "danger" : trace.fallback ? "warning" : "info"}>{trace.fallback ? "FALLBACK" : trace.source || "SOURCE"}</Badge>
                  </div>
                  <p>{trace.summary || trace.llm_error || "No summary recorded."}</p>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </article>
  );
}

export function MessageTimelinePanel({
  currentSession,
  messages,
  mutationError,
  sessionError,
  sessionStatus,
}: {
  currentSession?: AgentSession;
  messages: AgentMessage[];
  mutationError?: Error | null;
  sessionError?: Error | null;
  sessionStatus: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-8"
      eyebrow="Message Timeline"
      title={currentSession?.title || "No session selected"}
      description={currentSession?.summary || "Conversation, execution outputs, artifacts, repair traces, and knowledge context."}
      actions={<Badge tone={statusTone(sessionStatus)}>{displayStatus(sessionStatus)}</Badge>}
    >
      {sessionError ? (
        <InlineErrorState title="Agent session could not load" description={sessionError.message} />
      ) : currentSession ? (
        <div className="timeline">
          {messages.length ? messages.map((item) => (
            <MessageTimelineItem key={item.id} item={item} />
          )) : (
            <InlineEmptyState title="No messages yet" description="Use the composer to send the first instruction for this session." />
          )}
        </div>
      ) : (
        <InlineEmptyState title="No session selected" description="Create or select a session to start the Data Lab Agent loop." />
      )}
      {mutationError ? (
        <InlineErrorState title="Request failed" description={mutationError.message} />
      ) : null}
    </Surface>
  );
}
