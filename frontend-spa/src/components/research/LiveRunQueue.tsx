import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, MetricPill, RecordRow, Surface } from "../ui";
import type { RunSummary } from "./types";
import { statusTone } from "./viewHelpers";

type LiveRunQueueProps = {
  errorMessage?: string;
  isError: boolean;
  isSuccess: boolean;
  onSelectRun: (runId: string) => void;
  runs: RunSummary[];
  selectedRunId: string;
};

export function LiveRunQueue({
  errorMessage,
  isError,
  isSuccess,
  onSelectRun,
  runs,
  selectedRunId,
}: LiveRunQueueProps): JSX.Element {
  return (
    <Surface
      actions={<MetricPill label="Runs" value={isSuccess ? runs.length : "-"} />}
      className="ops-col-7"
      description="Queued and active jobs stay in polling until saved, blocked, or failed."
      eyebrow="Monitoring"
      title="Live Run Queue"
    >
      <div className="record-list">
        {isError ? (
          <InlineErrorState title="Recent runs could not load" description={errorMessage} />
        ) : null}
        {!isError && isSuccess && !runs.length ? (
          <InlineEmptyState title="No research runs yet" description="Start a run to populate monitoring, quality review, and publish controls." />
        ) : null}
        {runs.map((item) => (
          <RecordRow
            key={item.id}
            meta={`${item.queue_status || "queue unknown"} / ${item.current_stage || "stage unknown"}`}
            onClick={() => onSelectRun(item.id)}
            selected={selectedRunId === item.id}
            status={<Badge tone={statusTone(item.status)}>{item.status || "unknown"}</Badge>}
            title={item.topic || "Untitled run"}
          >
            {item.review_summary || item.current_stage || "Waiting for reviewer summary."}
          </RecordRow>
        ))}
      </div>
    </Surface>
  );
}

