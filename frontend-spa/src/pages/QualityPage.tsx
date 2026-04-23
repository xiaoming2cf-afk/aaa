import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api";

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

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Delivery Review</p>
            <h3>Scorecard</h3>
            <p>Publication is allowed only when the business score reaches 500/500 and the engineering gate is fully green.</p>
          </div>
          <div className={scorecardQuery.data?.deliverable ? "score-chip success" : "score-chip"}>
            {scorecardQuery.data?.total_score || 0}/500
          </div>
        </div>
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Workspace Deliverable</strong>
            <span>{scorecardQuery.data?.deliverable ? "PASS" : "BLOCKED"}</span>
          </div>
          <p>Business gate: {scorecardQuery.data?.business_deliverable ? "PASS" : "FAIL"} / Engineering gate: {scorecardQuery.data?.engineering_gate?.passed ? "PASS" : "FAIL"}</p>
          <p>{(scorecardQuery.data?.blocking_reasons || [])[0] || "No blocking reasons recorded."}</p>
        </div>
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>ARBITER Delivery Layer</strong>
            <span>{arbiterMeta.mode || "off"}</span>
          </div>
          <p>Recent delivery posteriors: {(arbiterMeta.recent_delivery_posteriors || []).length ? (arbiterMeta.recent_delivery_posteriors as number[]).map((item) => item.toFixed(3)).join(", ") : "none"}</p>
        </div>
        <div className="scorecard-grid">
          {(scorecardQuery.data?.dimensions || []).map((dimension: any) => (
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
        </div>
        <div className="score-card">
          <div className="score-card-head">
            <strong>Engineering Gate</strong>
            <span>{scorecardQuery.data?.engineering_gate?.passed ? "PASS" : "FAIL"}</span>
          </div>
          <ul className="plain-list">
            {(scorecardQuery.data?.engineering_gate?.checks || []).map((check: any) => (
              <li key={check.key}>{check.passed ? "PASS" : "FAIL"} / {check.label}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Recent Runs</p>
            <h3>Run Quality Snapshots</h3>
          </div>
        </div>
        <div className="list-stack">
          {(runsQuery.data?.items || []).map((item) => (
            <div key={item.run_id} className="list-card static-card">
              <div className="list-card-title">
                <strong>{item.run_id.slice(0, 8)}</strong>
                <span>{item.status}</span>
              </div>
              <p>citation {item.citation_coverage} / unsupported {item.unsupported_claim_rate} / review {item.review_block_precision}</p>
              <p>arbiter posterior {item.metadata?.arbiter?.delivery_posterior ?? "-"}</p>
              <p>{item.blocked_reason || "No blocking reason recorded."}</p>
            </div>
          ))}
          {!runsQuery.data?.items?.length ? (
            <div className="list-card static-card">
              <strong>No quality snapshots yet</strong>
              <p>Run research jobs first. Quality scoring is based on persisted run outcomes.</p>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
