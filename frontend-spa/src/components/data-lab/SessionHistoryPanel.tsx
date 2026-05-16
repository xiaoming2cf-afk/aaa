import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, RecordRow, Surface } from "../ui";
import { displayStatus, shortId, statusTone } from "./helpers";
import type { HistoryItem } from "./types";

export function SessionHistoryPanel({
  historyError,
  historyItems,
  historySuccess,
  selectedRunId,
  setSelectedRunId,
}: {
  historyError?: Error | null;
  historyItems: HistoryItem[];
  historySuccess: boolean;
  selectedRunId: string;
  setSelectedRunId: (value: string) => void;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Session History"
      title="Agent Sessions"
      description="Reopen a previous run or follow a deep-linked session."
    >
      <div className="record-list">
        {historyError ? (
          <InlineErrorState title="Agent sessions could not load" description={historyError.message} />
        ) : null}
        {!historyError && historySuccess && !historyItems.length ? (
          <InlineEmptyState title="No agent sessions yet" description="Create a session to begin the analysis loop." />
        ) : null}
        {historyItems.map((item) => {
          const runId = item.run_id || item.id;
          return (
            <RecordRow
              key={runId}
              selected={selectedRunId === runId}
              title={item.title}
              status={<Badge tone={statusTone(item.status)}>{displayStatus(item.status)}</Badge>}
              meta={`Run ${shortId(runId)}`}
              onClick={() => setSelectedRunId(runId)}
            >
              {item.summary || "Open the session to inspect messages and cells."}
            </RecordRow>
          );
        })}
      </div>
    </Surface>
  );
}
