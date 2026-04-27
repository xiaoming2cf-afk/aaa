import { RefreshCw, UploadCloud } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, MetricPill, Surface } from "../ui";
import { blockingReasons, formatDate, sourceLabel, sourceType } from "./types";
import type { KnowledgeRecord } from "./types";

export function KnowledgeRecordsPanel({
  blockedCount,
  isError,
  isLoading,
  isSuccess,
  onPublish,
  onRetry,
  publishError,
  publishing,
  readyCount,
  records,
  teamId,
  teamName,
}: {
  blockedCount: number;
  isError: boolean;
  isLoading: boolean;
  isSuccess: boolean;
  onPublish: (recordId: string) => void;
  onRetry: () => void;
  publishError?: Error | null;
  publishing: boolean;
  readyCount: number;
  records: KnowledgeRecord[];
  teamId: string;
  teamName?: string;
}): JSX.Element {
  return (
    <Surface
      actions={(
        <div className="metric-strip">
          <MetricPill label="Records" value={records.length} />
          <MetricPill label="Ready" tone="success" value={readyCount} />
          <MetricPill label="Blocked" tone={blockedCount ? "warning" : "neutral"} value={blockedCount} />
        </div>
      )}
      className="ops-col-7"
      description="Publication status is read from the delivery review gate; blocked rows keep their first recorded reason visible."
      eyebrow="Knowledge Base"
      title="Records"
    >
      <div className="list-stack">
        {isLoading ? (
          <div className="list-card static-card inline-state" role="status" aria-live="polite">
            <strong>Loading knowledge records</strong>
            <p>Fetching workspace notes and publication gate metadata.</p>
          </div>
        ) : null}
        {isError ? (
          <InlineErrorState
            title="Knowledge records could not load"
            description="The knowledge API did not return records for this workspace."
            action={(
              <Button icon={<RefreshCw />} variant="ghost" onClick={onRetry}>
                Retry records
              </Button>
            )}
          />
        ) : null}
        {!isError && isSuccess && !records.length ? (
          <InlineEmptyState title="No knowledge records yet" description="Create a workspace note or publish reviewed research to build the knowledge base." />
        ) : null}
        {records.length ? (
          <div className="ops-table-scroll">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Publication</th>
                  <th>Metadata</th>
                  <th>Gate</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {records.map((item) => (
                  <KnowledgeRecordRow
                    item={item}
                    key={item.id}
                    onPublish={onPublish}
                    publishing={publishing}
                    teamId={teamId}
                    teamName={teamName}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {publishError ? (
          <InlineErrorState title="Knowledge record was not published" description={publishError.message} />
        ) : null}
      </div>
    </Surface>
  );
}

function KnowledgeRecordRow({
  item,
  onPublish,
  publishing,
  teamId,
  teamName,
}: {
  item: KnowledgeRecord;
  onPublish: (recordId: string) => void;
  publishing: boolean;
  teamId: string;
  teamName?: string;
}): JSX.Element {
  const blockers = blockingReasons(item);
  const publishAllowed = Boolean(item.publish_allowed);
  const gateMessage = publishAllowed
    ? "Publish is allowed."
    : blockers[0] || "Publish is blocked until delivery review reaches 100%.";
  const gateScore = typeof item.delivery_review?.total_score === "number"
    ? `${item.delivery_review.total_score}/500`
    : "score pending";

  return (
    <tr>
      <td>
        <div className="record-row-main">
          <strong>{item.title}</strong>
          <span>{item.content_excerpt || item.content || ""}</span>
          <small>ID {item.id.slice(0, 8)}</small>
          {item.tags?.length ? (
            <span className="inline-metrics">
              {item.tags.slice(0, 4).map((tag) => (
                <span key={`${item.id}-${tag}`}>{tag}</span>
              ))}
            </span>
          ) : null}
        </div>
      </td>
      <td>
        <Badge tone={publishAllowed ? "success" : "warning"}>
          {publishAllowed ? "Ready" : "Blocked"}
        </Badge>
      </td>
      <td>
        <div className="record-row-main">
          <span>{sourceType(item)}</span>
          <small>Source: {sourceLabel(item)}</small>
          <small>Updated: {formatDate(item.updated_at || item.created_at)}</small>
        </div>
      </td>
      <td>
        <div className="record-row-main">
          <span>{gateMessage}</span>
          <small>{gateScore}</small>
        </div>
      </td>
      <td>
        <div className="list-stack">
          <div className="record-row-main">
            <span>Team</span>
            <small>{teamName || (teamId ? teamId.slice(0, 8) : "No team selected")}</small>
          </div>
          <Button
            disabled={!teamId || !publishAllowed}
            icon={<UploadCloud />}
            loading={publishing}
            onClick={() => onPublish(item.id)}
            variant="ghost"
          >
            Publish
          </Button>
        </div>
      </td>
    </tr>
  );
}
