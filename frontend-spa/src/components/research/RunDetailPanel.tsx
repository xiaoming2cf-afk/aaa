import { RefreshCw, Send, ShieldAlert } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, CodeBlock, Field, JsonBlock, MetricPill, Surface } from "../ui";
import type { ResearchTeam, RunDetail, RunDetailTab } from "./types";
import { firstBlocker, formatValue, gateLabel, gateTone, statusTone } from "./viewHelpers";

const RUN_DETAIL_TABS: Array<{ id: RunDetailTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "evidence", label: "Evidence" },
  { id: "review", label: "Review" },
  { id: "arbiter", label: "ARBITER" },
  { id: "report", label: "Final Report" },
];

type RunDetailPanelProps = {
  arbiterMode: string;
  candidateDrafts: Array<any>;
  detailErrorMessage?: string;
  detailTab: RunDetailTab;
  onDetailTabChange: (tab: RunDetailTab) => void;
  onPublish: () => void;
  onRetry: () => void;
  onRetryInstructionsChange: (value: string) => void;
  onTeamChange: (value: string) => void;
  publishAllowed: boolean;
  publishBlockers: string[];
  publishErrorMessage?: string;
  publishGate?: boolean;
  publishPending: boolean;
  retryErrorMessage?: string;
  retryInstructions: string;
  retryPending: boolean;
  scoreSummary: Record<string, any>;
  selectedRun?: RunDetail;
  selectedRunId: string;
  selectionTrace: any;
  teamId: string;
  teams: ResearchTeam[];
};

export function RunDetailPanel({
  arbiterMode,
  candidateDrafts,
  detailErrorMessage,
  detailTab,
  onDetailTabChange,
  onPublish,
  onRetry,
  onRetryInstructionsChange,
  onTeamChange,
  publishAllowed,
  publishBlockers,
  publishErrorMessage,
  publishGate,
  publishPending,
  retryErrorMessage,
  retryInstructions,
  retryPending,
  scoreSummary,
  selectedRun,
  selectedRunId,
  selectionTrace,
  teamId,
  teams,
}: RunDetailPanelProps): JSX.Element {
  const publishGateTitle = publishAllowed ? "Publish gate open" : publishGate === undefined ? "Publish gate is unknown" : "Publication blocked";
  const publishGateDescription = publishAllowed
    ? "This run can be published to the selected team library."
    : firstBlocker(
      publishBlockers,
      publishGate === undefined ? "Publish gate state is unknown until delivery review returns a current result." : "The delivery review has not yet reached 100%.",
    );

  return (
    <Surface
      actions={(
        <div className="metric-strip">
          <MetricPill label="Citation" value={formatValue(scoreSummary.citation_coverage)} />
          <MetricPill label="Unsupported" value={formatValue(scoreSummary.unsupported_claim_rate)} />
          <MetricPill label="Review Precision" value={formatValue(scoreSummary.review_block_precision)} />
        </div>
      )}
      eyebrow="Trace"
      span
      title="Run Detail"
    >
      {detailErrorMessage ? (
        <InlineErrorState title="Run detail could not load" description={detailErrorMessage} />
      ) : selectedRun ? (
        <>
          <div className="metric-strip">
            <MetricPill label="Run Status" tone={statusTone(selectedRun.status)} value={selectedRun.status || "unknown"} />
            <MetricPill label="Queue" tone={statusTone(selectedRun.queue_status)} value={selectedRun.queue_status || "unknown"} />
            <MetricPill label="Publish Gate" tone={gateTone(publishGate)} value={publishAllowed ? "OPEN" : gateLabel(publishGate)} />
            <MetricPill label="Quality" value={formatValue(selectedRun.quality_summary?.quality_score)} />
          </div>

          <div className="ops-tabs" role="tablist" aria-label="Run detail sections">
            {RUN_DETAIL_TABS.map((tab) => (
              <button
                key={tab.id}
                aria-selected={detailTab === tab.id}
                className={detailTab === tab.id ? "ops-tab active" : "ops-tab"}
                onClick={() => onDetailTabChange(tab.id)}
                role="tab"
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>

          {detailTab === "overview" ? (
            <div className="detail-grid">
              <div className="detail-column">
                <table className="ops-table">
                  <tbody>
                    <tr>
                      <th scope="row">Run</th>
                      <td>{selectedRun.id}</td>
                    </tr>
                    <tr>
                      <th scope="row">Topic</th>
                      <td>{selectedRun.topic || "Untitled run"}</td>
                    </tr>
                    <tr>
                      <th scope="row">Stage</th>
                      <td>{selectedRun.current_stage || "unknown"}</td>
                    </tr>
                    <tr>
                      <th scope="row">Attachments</th>
                      <td>{selectedRun.attachments?.length ?? 0}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="detail-column">
                <div className={publishAllowed ? "list-card static-card inline-state" : "list-card static-card inline-state-error"} role={publishAllowed ? "status" : "alert"}>
                  <div className="list-card-title">
                    <strong>{publishGateTitle}</strong>
                    <Badge tone={gateTone(publishGate)}>{publishAllowed ? "OPEN" : gateLabel(publishGate)}</Badge>
                  </div>
                  <p>{publishGateDescription}</p>
                </div>
                <div className="list-card static-card">
                  <div className="list-card-title">
                    <strong>Delivery Review</strong>
                    <Badge tone={gateTone(selectedRun.delivery_review?.deliverable)}>{gateLabel(selectedRun.delivery_review?.deliverable)}</Badge>
                  </div>
                  <p>{selectedRun.review_summary || "No reviewer summary has been persisted yet."}</p>
                </div>
                <div className="list-card static-card">
                  <div className="list-card-title">
                    <strong>ARBITER Candidates</strong>
                    <Badge tone="info">{arbiterMode}</Badge>
                  </div>
                  {selectionTrace?.comparison ? (
                    <p>
                      baseline {selectionTrace.baseline_draft_id || "none"} / proposed {selectionTrace.proposed_draft_id || "none"} / chosen {selectionTrace.chosen_draft_id || "none"}
                    </p>
                  ) : (
                    <p>No selection-level ARBITER trace was persisted for this run.</p>
                  )}
                  {candidateDrafts[0] ? (() => {
                    const candidate = candidateDrafts.find((item) => item.draft_id === selectionTrace?.chosen_draft_id) || candidateDrafts[0];
                    const arbiter = candidate?.metadata?.arbiter || {};
                    const v2 = arbiter.v2 || {};
                    return (
                      <small>
                        mode {arbiter.mode || arbiterMode} / baseline score {arbiter.baseline_score ?? candidate.score ?? "-"} / baseline utility {arbiter.utility ?? "-"} / v2 utility {v2.utility ?? "-"} / revision cost {v2.revision_cost ?? "-"} / risk {arbiter.risk ?? "-"}
                      </small>
                    );
                  })() : null}
                </div>
              </div>
            </div>
          ) : null}

          {detailTab === "evidence" ? (
            <div className="detail-grid">
              <JsonBlock label="Evidence" value={selectedRun.evidence || {}} />
              <JsonBlock label="Trace" value={selectedRun.trace || []} />
            </div>
          ) : null}

          {detailTab === "review" ? (
            <div className="detail-grid">
              <JsonBlock label="Review" value={selectedRun.review || {}} />
              <JsonBlock label="Delivery Review" value={selectedRun.delivery_review || {}} />
            </div>
          ) : null}

          {detailTab === "arbiter" ? (
            <div className="detail-grid">
              <div className="detail-column">
                <h4>ARBITER Candidates</h4>
                {selectionTrace?.comparison ? (
                  <div className="list-card static-card">
                    <div className="list-card-title">
                      <strong>Selection v2</strong>
                      <Badge tone="info">{selectionTrace.mode || arbiterMode}</Badge>
                    </div>
                    <p>
                      baseline {selectionTrace.baseline_draft_id || "none"} / proposed {selectionTrace.proposed_draft_id || "none"} / chosen {selectionTrace.chosen_draft_id || "none"}
                    </p>
                    <small>
                      advantage {formatValue(selectionTrace.comparison?.advantage)} / margin {formatValue(selectionTrace.comparison?.override_margin)} / fallback {selectionTrace.comparison?.fallback_reason || "override_applied"}
                    </small>
                  </div>
                ) : (
                  <p className="muted">No selection-level ARBITER trace was persisted for this run.</p>
                )}
              </div>
              <div className="detail-column">
                {candidateDrafts.length ? (
                  <div className="record-list">
                    {candidateDrafts.map((candidate) => {
                      const arbiter = candidate?.metadata?.arbiter || {};
                      const v2 = arbiter.v2 || {};
                      return (
                        <div key={candidate.draft_id} className="list-card static-card">
                          <div className="list-card-title">
                            <strong>{candidate.draft_id}</strong>
                            <Badge tone={statusTone(candidate.status)}>{candidate.status || "unknown"}</Badge>
                          </div>
                          <p>{candidate.summary || "No reviewer summary."}</p>
                          <small>
                            mode {arbiter.mode || arbiterMode} / baseline score {formatValue(arbiter.baseline_score ?? candidate.score)} / baseline utility {formatValue(arbiter.utility)} / v2 utility {formatValue(v2.utility)} / revision cost {formatValue(v2.revision_cost)} / risk {formatValue(arbiter.risk)}
                          </small>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="muted">No candidate-level ARBITER traces were persisted for this run.</p>
                )}
              </div>
            </div>
          ) : null}

          {detailTab === "report" ? (
            <CodeBlock label="Final Report">{selectedRun.final_text || "No final report persisted yet."}</CodeBlock>
          ) : null}

          <div className="action-row">
            <Field label="Retry Instructions" span>
              <textarea value={retryInstructions} onChange={(event) => onRetryInstructionsChange(event.target.value)} rows={3} />
            </Field>
            <Button icon={<RefreshCw />} disabled={!selectedRunId || retryPending} onClick={onRetry} variant="ghost">
              Retry Writer/Reviewer
            </Button>
            <Field label="Team">
              <select value={teamId} disabled={!teams.length} onChange={(event) => onTeamChange(event.target.value)}>
                <option value="">{teams.length ? "Select team" : "No team"}</option>
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>{team.name}</option>
                ))}
              </select>
            </Field>
            <Button
              disabled={!teamId || publishPending || !selectedRunId || !publishAllowed}
              icon={<Send />}
              onClick={onPublish}
              variant="primary"
            >
              Publish to Team Library
            </Button>
          </div>

          {!publishAllowed ? (
            <div className="list-card static-card inline-state-error" role="alert">
              <div className="list-card-title">
                <strong>Publish is blocked</strong>
                <ShieldAlert aria-hidden="true" size={17} />
              </div>
              <p>{publishGateDescription}</p>
            </div>
          ) : null}
          {retryErrorMessage ? (
            <InlineErrorState title="Retry failed" description={retryErrorMessage} />
          ) : null}
          {publishErrorMessage ? (
            <InlineErrorState title="Publish failed" description={publishErrorMessage} />
          ) : null}
        </>
      ) : (
        <InlineEmptyState title="No run selected" description="Select a run to inspect evidence, review, trace, and final report." />
      )}
    </Surface>
  );
}
