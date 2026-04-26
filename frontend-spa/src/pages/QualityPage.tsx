import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api";
import { InlineEmptyState, InlineErrorState } from "../components/StatusPrimitives";

type UseAppState = () => {
  workspaceId: string;
};

export function QualityPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();

  const scorecardQuery = useQuery({
    queryKey: ["quality-scorecard", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<any>(`/api/workspaces/${workspaceId}/quality/scorecard`),
  });

  const runsQuery = useQuery({
    queryKey: ["quality-runs", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: any[] }>(`/api/workspaces/${workspaceId}/quality/runs`),
  });

  const arbiterMeta = scorecardQuery.data?.metadata?.arbiter || {};
  const arbiterV2 = arbiterMeta.v2 || {};
  const scorecard = scorecardQuery.data;
  const scorecardReady = scorecardQuery.isSuccess && Boolean(scorecard);
  const scorecardUnavailable = scorecardQuery.isLoading || scorecardQuery.isError;
  const scoreChipLabel = scorecardQuery.isLoading
    ? "Loading"
    : scorecardQuery.isError
      ? "Unavailable"
      : `${scorecard?.total_score ?? 0}/500`;
  const scorecardStatus = scorecardUnavailable
    ? "UNKNOWN"
    : scorecard?.deliverable
      ? "PASS"
      : "BLOCKED";

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Delivery Review</p>
            <h3>Scorecard</h3>
            <p>Publication is allowed only when the business score reaches 500/500 and the engineering gate is fully green.</p>
          </div>
          <div className={scorecard?.deliverable ? "score-chip success" : "score-chip"}>
            {scoreChipLabel}
          </div>
        </div>
        {scorecardQuery.isLoading ? (
          <div className="list-card static-card inline-state" role="status" aria-live="polite">
            <strong>Checking delivery status</strong>
            <p>Loading business and engineering gate results for this workspace.</p>
          </div>
        ) : null}
        {scorecardQuery.isError ? (
          <InlineErrorState
            title="Delivery status unavailable"
            description={(scorecardQuery.error as Error).message}
            action={(
              <button className="ghost-button" type="button" onClick={() => void scorecardQuery.refetch()}>
                Retry scorecard
              </button>
            )}
          />
        ) : null}
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Workspace Deliverable</strong>
            <span>{scorecardStatus}</span>
          </div>
          {scorecardReady ? (
            <>
              <p>Business gate: {scorecard.business_deliverable ? "PASS" : "FAIL"} / Engineering gate: {scorecard.engineering_gate?.passed ? "PASS" : "FAIL"}</p>
              <p>{(scorecard.blocking_reasons || [])[0] || "No blocking reasons recorded."}</p>
            </>
          ) : (
            <p>Gate state is unknown until the quality API returns a current scorecard.</p>
          )}
        </div>
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>ARBITER Delivery Layer</strong>
            <span>{arbiterMeta.mode || "off"}</span>
          </div>
          <p>Recent delivery posteriors: {(arbiterMeta.recent_delivery_posteriors || []).length ? (arbiterMeta.recent_delivery_posteriors as number[]).map((item) => item.toFixed(3)).join(", ") : "none"}</p>
          <p>Recent v2 posteriors: {(arbiterV2.recent_delivery_posteriors || []).length ? (arbiterV2.recent_delivery_posteriors as number[]).map((item) => item.toFixed(3)).join(", ") : "none"}</p>
          <p>Recent v2 choices: {(arbiterV2.recent_choices || []).length ? (arbiterV2.recent_choices as boolean[]).map((item) => (item ? "deliver" : "block")).join(", ") : "none"}</p>
        </div>
        <div className="scorecard-grid">
          {(scorecard?.dimensions || []).map((dimension: any) => (
            <div key={dimension.key} className="score-card">
              <div className="score-card-head">
                <strong>{dimension.label}</strong>
                <span>{dimension.score}/100</span>
              </div>
              <ul className="plain-list">
                {(dimension.checks || []).map((check: any) => (
                  <li key={check.key}>{check.passed ? "PASS" : "FAIL"} / {check.label}</li>
                ))}
              </ul>
            </div>
          ))}
          {scorecardQuery.isSuccess && !scorecard?.dimensions?.length ? (
            <InlineEmptyState title="No scorecard dimensions yet" description="Run quality scoring to populate delivery dimensions and checks." />
          ) : null}
        </div>
        {scorecardReady ? (
          <div className="score-card">
            <div className="score-card-head">
              <strong>Engineering Gate</strong>
              <span>{scorecard.engineering_gate?.passed ? "PASS" : "FAIL"}</span>
            </div>
            <ul className="plain-list">
              {(scorecard.engineering_gate?.checks || []).map((check: any) => (
                <li key={check.key}>{check.passed ? "PASS" : "FAIL"} / {check.label}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Recent Runs</p>
            <h3>Run Quality Snapshots</h3>
          </div>
        </div>
        <div className="list-stack">
          {runsQuery.isLoading ? (
            <div className="list-card static-card inline-state" role="status" aria-live="polite">
              <strong>Loading quality snapshots</strong>
              <p>Fetching recent persisted run outcomes.</p>
            </div>
          ) : null}
          {runsQuery.isError ? (
            <InlineErrorState
              title="Quality snapshots could not load"
              description={(runsQuery.error as Error).message}
              action={(
                <button className="ghost-button" type="button" onClick={() => void runsQuery.refetch()}>
                  Retry snapshots
                </button>
              )}
            />
          ) : null}
          {(runsQuery.data?.items || []).map((item) => (
            <div key={item.run_id} className="list-card static-card">
              <div className="list-card-title">
                <strong>{item.run_id.slice(0, 8)}</strong>
                <span>{item.status}</span>
              </div>
              <p>citation {item.citation_coverage} / unsupported {item.unsupported_claim_rate} / review {item.review_block_precision}</p>
              <p>arbiter posterior {item.metadata?.arbiter?.delivery_posterior ?? "-"}</p>
              <p>arbiter v2 posterior {item.metadata?.arbiter?.v2?.delivery_posterior ?? "-"}</p>
              <p>arbiter v2 fallback {item.metadata?.arbiter?.v2?.comparison?.fallback_reason || "override_applied"}</p>
              <p>{item.blocked_reason || "No blocking reason recorded."}</p>
            </div>
          ))}
          {!runsQuery.isError && runsQuery.isSuccess && !runsQuery.data?.items?.length ? (
            <InlineEmptyState title="No quality snapshots yet" description="Run research jobs first. Quality scoring is based on persisted run outcomes." />
          ) : null}
        </div>
      </section>
    </div>
  );
}
