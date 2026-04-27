import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api";
import {
  ArbiterTrend,
  GateMatrix,
  QualityRadar,
  SnapshotsTable,
  boolValue,
  checkSummary,
  clampPercent,
  dimensionGateState,
  gateLabel,
  type GateRow,
  type QualityDimension,
  type QualityRunSnapshot,
  type QualityScorecard,
} from "../components/quality";

type UseAppState = () => {
  workspaceId: string;
};

export function QualityPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();

  const scorecardQuery = useQuery({
    queryKey: ["quality-scorecard", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<QualityScorecard>(`/api/workspaces/${workspaceId}/quality/scorecard`),
  });

  const runsQuery = useQuery({
    queryKey: ["quality-runs", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: QualityRunSnapshot[] }>(`/api/workspaces/${workspaceId}/quality/runs`),
  });

  const scorecard = scorecardQuery.data;
  const scorecardReady = scorecardQuery.isSuccess && Boolean(scorecard);
  const arbiterMeta = scorecard?.metadata?.arbiter || {};
  const arbiterV2 = arbiterMeta.v2 || {};
  const dimensions = (scorecard?.dimensions || []) as QualityDimension[];
  const engineeringGate = scorecard?.engineering_gate;
  const workspaceDeliverable = scorecardReady ? boolValue(scorecard?.deliverable) : undefined;
  const businessGate = scorecardReady ? boolValue(scorecard?.business_deliverable) : undefined;
  const engineeringGateState = scorecardReady ? boolValue(engineeringGate?.passed) : undefined;
  const totalScore = scorecardReady ? Number(scorecard?.total_score ?? 0) : 0;
  const scorePercent = clampPercent((totalScore / 500) * 100);
  const scoreChipLabel = !workspaceId
    ? "No workspace"
    : scorecardQuery.isLoading
      ? "Loading"
      : scorecardQuery.isError
        ? "Unavailable"
        : `${scorecard?.total_score ?? 0}/500`;
  const scorecardStatus = scorecardReady ? gateLabel(workspaceDeliverable, "BLOCKED") : "UNKNOWN";
  const blockingReasons = scorecard?.blocking_reasons || [];
  const gateRows: GateRow[] = [
    {
      key: "business",
      label: "Business Gate",
      score: scorecardReady ? scorePercent : undefined,
      state: businessGate,
      summary: scorecardReady ? "Business score must reach 500/500." : "Gate state is unknown until scorecard loads.",
    },
    ...dimensions.map((dimension) => ({
      key: dimension.key,
      label: dimension.label,
      score: typeof dimension.score === "number" ? clampPercent(dimension.score) : undefined,
      state: dimensionGateState(dimension),
      summary: checkSummary(dimension.checks),
    })),
    {
      key: "engineering",
      label: "Engineering Control",
      score: engineeringGateState === true ? 100 : engineeringGateState === false ? 0 : undefined,
      state: engineeringGateState,
      summary: engineeringGate?.checks?.length ? checkSummary(engineeringGate.checks) : `Source: ${engineeringGate?.source || "unknown"}`,
    },
  ];
  const trendPosteriors = (arbiterV2.recent_delivery_posteriors?.length ? arbiterV2.recent_delivery_posteriors : arbiterMeta.recent_delivery_posteriors) || [];
  const trendChoices = arbiterV2.recent_choices || [];
  const snapshotItems = runsQuery.data?.items || [];

  return (
    <div className="ops-grid">
      <QualityRadar
        blockingReasons={blockingReasons}
        businessGate={businessGate}
        engineeringGateState={engineeringGateState}
        errorMessage={scorecardQuery.isError ? (scorecardQuery.error as Error).message : undefined}
        isError={scorecardQuery.isError}
        isLoading={scorecardQuery.isLoading}
        onRetryScorecard={() => void scorecardQuery.refetch()}
        scoreChipLabel={scoreChipLabel}
        scorePercent={scorePercent}
        scorecardReady={scorecardReady}
        scorecardStatus={scorecardStatus}
        totalScore={totalScore}
        workspaceDeliverable={workspaceDeliverable}
        workspaceId={workspaceId}
      />
      <GateMatrix
        dimensions={dimensions}
        engineeringGate={engineeringGate}
        engineeringGateState={engineeringGateState}
        gateRows={gateRows}
        scorecardReady={scorecardReady}
      />
      <ArbiterTrend
        arbiterMode={arbiterMeta.mode}
        trendChoices={trendChoices}
        trendPosteriors={trendPosteriors}
        v2SampleCount={arbiterV2.recent_delivery_posteriors?.length || 0}
      />
      <SnapshotsTable
        errorMessage={runsQuery.isError ? (runsQuery.error as Error).message : undefined}
        isError={runsQuery.isError}
        isLoading={runsQuery.isLoading}
        isSuccess={runsQuery.isSuccess}
        items={snapshotItems}
        onRetrySnapshots={() => void runsQuery.refetch()}
      />
    </div>
  );
}
