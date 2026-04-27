import type { CSSProperties } from "react";
import { Gauge, RefreshCw } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, MetricPill, Surface } from "../ui";
import { gateLabel, gateTone } from "./viewHelpers";

type QualityRadarProps = {
  blockingReasons: string[];
  businessGate?: boolean;
  engineeringGateState?: boolean;
  errorMessage?: string;
  isError: boolean;
  isLoading: boolean;
  onRetryScorecard: () => void;
  scoreChipLabel: string;
  scorePercent: number;
  scorecardReady: boolean;
  scorecardStatus: string;
  totalScore: number;
  workspaceDeliverable?: boolean;
  workspaceId: string;
};

export function QualityRadar({
  blockingReasons,
  businessGate,
  engineeringGateState,
  errorMessage,
  isError,
  isLoading,
  onRetryScorecard,
  scoreChipLabel,
  scorePercent,
  scorecardReady,
  scorecardStatus,
  totalScore,
  workspaceDeliverable,
  workspaceId,
}: QualityRadarProps): JSX.Element {
  const radarStyle = { "--score": `${scorePercent * 3.6}deg` } as CSSProperties;

  return (
    <Surface
      actions={<MetricPill label="Score" tone={gateTone(workspaceDeliverable)} value={scoreChipLabel} />}
      className="ops-col-5"
      description="Publication is allowed only when the business score reaches 500/500 and the engineering gate is fully green."
      eyebrow="Delivery Review"
      title={<><Gauge aria-hidden="true" size={18} /> Quality Radar</>}
      tone="emphasis"
    >
      <div className="quality-radar">
        <div className="quality-radar-ring" style={radarStyle} aria-label={`Quality score ${scorecardReady ? `${totalScore} of 500` : "unknown"}`}>
          <strong>{scorecardReady ? totalScore : "?"}</strong>
        </div>
        <div className="gate-matrix">
          <div className="list-card static-card">
            <div className="list-card-title">
              <strong>Workspace Deliverable</strong>
              <Badge tone={gateTone(workspaceDeliverable)}>{scorecardStatus}</Badge>
            </div>
            {scorecardReady ? (
              <>
                <p>Business gate: {gateLabel(businessGate)} / Engineering gate: {gateLabel(engineeringGateState)}</p>
                <p>{blockingReasons[0] || "No blocking reasons recorded."}</p>
              </>
            ) : (
              <p>Gate state is unknown until the quality API returns a current scorecard.</p>
            )}
          </div>
          <div className="metric-strip">
            <MetricPill label="Business" tone={gateTone(businessGate)} value={businessGate === undefined ? "Not known" : gateLabel(businessGate)} />
            <MetricPill label="Engineering" tone={gateTone(engineeringGateState)} value={engineeringGateState === undefined ? "Not known" : gateLabel(engineeringGateState)} />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="list-card static-card inline-state" role="status" aria-live="polite">
          <strong>Checking delivery status</strong>
          <p>Loading business and engineering gate results for this workspace.</p>
        </div>
      ) : null}
      {isError ? (
        <InlineErrorState
          title="Delivery status unavailable"
          description={errorMessage}
          action={(
            <Button icon={<RefreshCw />} onClick={onRetryScorecard} variant="ghost">
              Retry scorecard
            </Button>
          )}
        />
      ) : null}
      {!workspaceId ? (
        <InlineEmptyState title="No workspace selected" description="Select a workspace before reading quality delivery gates." />
      ) : null}
    </Surface>
  );
}
