import { Table2, RefreshCw } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, MetricPill, Surface } from "../ui";
import type { QualityRunSnapshot } from "./types";
import { boolValue, formatValue, gateTone, statusTone } from "./viewHelpers";

export function SnapshotsTable({
  errorMessage,
  isError,
  isLoading,
  isSuccess,
  items,
  onRetrySnapshots,
}: {
  errorMessage?: string;
  isError: boolean;
  isLoading: boolean;
  isSuccess: boolean;
  items: QualityRunSnapshot[];
  onRetrySnapshots: () => void;
}): JSX.Element {
  return (
    <Surface
      actions={<MetricPill label="Snapshots" value={isSuccess ? items.length : "-"} />}
      className="ops-col-7"
      description="Persisted run-level quality outcomes for recent research jobs."
      eyebrow="Recent Snapshots"
      title={<><Table2 aria-hidden="true" size={18} /> Recent Snapshots Table</>}
    >
      {isLoading ? (
        <div className="list-card static-card inline-state" role="status" aria-live="polite">
          <strong>Loading quality snapshots</strong>
          <p>Fetching recent persisted run outcomes.</p>
        </div>
      ) : null}
      {isError ? (
        <InlineErrorState
          title="Quality snapshots could not load"
          description={errorMessage}
          action={(
            <Button icon={<RefreshCw />} onClick={onRetrySnapshots} variant="ghost">
              Retry snapshots
            </Button>
          )}
        />
      ) : null}
      {!isError && isSuccess && !items.length ? (
        <InlineEmptyState title="No quality snapshots yet" description="Run research jobs first. Quality scoring is based on persisted run outcomes." />
      ) : null}
      {items.length ? (
        <div className="ops-table-scroll">
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Status</th>
                <th scope="col">Publish</th>
                <th scope="col">Citation</th>
                <th scope="col">Unsupported</th>
                <th scope="col">Review Precision</th>
                <th scope="col">ARBITER</th>
                <th scope="col">Blocker</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const publishState = boolValue(item.publish_allowed);
                return (
                  <tr key={item.run_id}>
                    <td>{item.run_id.slice(0, 8)}</td>
                    <td><Badge tone={statusTone(item.status)}>{item.status || "unknown"}</Badge></td>
                    <td><Badge tone={gateTone(publishState)}>{publishState === true ? "ALLOWED" : publishState === false ? "BLOCKED" : "UNKNOWN"}</Badge></td>
                    <td>{formatValue(item.citation_coverage)}</td>
                    <td>{formatValue(item.unsupported_claim_rate)}</td>
                    <td>{formatValue(item.review_block_precision)}</td>
                    <td>
                      arbiter posterior {formatValue(item.metadata?.arbiter?.delivery_posterior)}
                      <br />
                      arbiter v2 posterior {formatValue(item.metadata?.arbiter?.v2?.delivery_posterior)}
                    </td>
                    <td>{item.blocked_reason || item.metadata?.arbiter?.v2?.comparison?.fallback_reason || "No blocking reason recorded."}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </Surface>
  );
}
