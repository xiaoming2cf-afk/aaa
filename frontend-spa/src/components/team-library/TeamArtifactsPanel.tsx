import { CopyPlus, RefreshCw } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, JsonBlock, MetricPill, Surface } from "../ui";
import { formatDate, metadataString } from "./types";
import type { TeamLibraryRecord } from "./types";

export function TeamArtifactsPanel({
  cloneError,
  clonePending,
  currentTeamName,
  isError,
  isLoading,
  isSuccess,
  items,
  onClone,
  onRetry,
  teamId,
  teamsCount,
  workspaceId,
}: {
  cloneError?: Error | null;
  clonePending: boolean;
  currentTeamName?: string;
  isError: boolean;
  isLoading: boolean;
  isSuccess: boolean;
  items: TeamLibraryRecord[];
  onClone: (recordId: string) => void;
  onRetry: () => void;
  teamId: string;
  teamsCount: number;
  workspaceId: string;
}): JSX.Element {
  return (
    <Surface
      actions={(
        <div className="metric-strip">
          <MetricPill label="Teams" value={teamsCount} />
          <MetricPill label="Artifacts" value={items.length} />
          <MetricPill label="Workspace" tone={workspaceId ? "info" : "warning"} value={workspaceId ? "selected" : "none"} />
        </div>
      )}
      className="ops-col-7"
      description={currentTeamName ? `Browsing published artifacts for ${currentTeamName}.` : "Select a team before loading published artifacts."}
      eyebrow="Published Artifacts"
      title="Team Library"
    >
      {!teamId ? (
        <InlineEmptyState title="No team selected" description="Choose or create a team to browse published records." />
      ) : (
        <div className="list-stack">
          {isLoading ? (
            <div className="list-card static-card inline-state" role="status" aria-live="polite">
              <strong>Loading team library</strong>
              <p>Fetching published records for the selected team.</p>
            </div>
          ) : null}
          {isError ? (
            <InlineErrorState
              title="Team library could not load"
              description="The selected team library API did not return published artifacts."
              action={(
                <Button icon={<RefreshCw />} variant="ghost" onClick={onRetry}>
                  Retry library
                </Button>
              )}
            />
          ) : null}
          {!isError && isSuccess && !items.length ? (
            <InlineEmptyState title="No published records yet" description="Publish a reviewed knowledge record before the team library can serve reusable artifacts." />
          ) : null}
          {items.length ? (
            <div className="ops-table-scroll">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Artifact</th>
                    <th>Status</th>
                    <th>Metadata</th>
                    <th>Source</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <ArtifactRow
                      item={item}
                      key={item.id}
                      onClone={onClone}
                      clonePending={clonePending}
                      workspaceId={workspaceId}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      )}
      {cloneError ? (
        <InlineErrorState title="Library record was not cloned" description={cloneError.message} />
      ) : null}
    </Surface>
  );
}

function ArtifactRow({
  clonePending,
  item,
  onClone,
  workspaceId,
}: {
  clonePending: boolean;
  item: TeamLibraryRecord;
  onClone: (recordId: string) => void;
  workspaceId: string;
}): JSX.Element {
  const sourceRunId = metadataString(item, "source_run_id");
  const sourceRecordId = metadataString(item, "source_record_id");
  const sourceWorkspaceId = metadataString(item, "workspace_id");

  return (
    <tr>
      <td>
        <div className="record-row-main">
          <strong>{item.title}</strong>
          <span>{item.summary || "No summary recorded."}</span>
          <small>ID {item.id.slice(0, 8)}</small>
        </div>
      </td>
      <td>
        <Badge tone="success">Published</Badge>
      </td>
      <td>
        <div className="record-row-main">
          <span>{item.source_type || metadataString(item, "source_type") || "knowledge"}</span>
          <small>Published: {formatDate(item.published_at || item.updated_at || item.created_at)}</small>
          <details>
            <summary>Metadata</summary>
            <JsonBlock value={item.metadata || {}} />
          </details>
        </div>
      </td>
      <td>
        <div className="record-row-main">
          <span>{sourceRunId ? `Run ${sourceRunId.slice(0, 8)}` : "Run not recorded"}</span>
          <small>{sourceRecordId ? `Record ${sourceRecordId.slice(0, 8)}` : "Source record not recorded"}</small>
          <small>{sourceWorkspaceId ? `Workspace ${sourceWorkspaceId.slice(0, 8)}` : "Workspace metadata not recorded"}</small>
        </div>
      </td>
      <td>
        <Button
          disabled={!workspaceId}
          icon={<CopyPlus />}
          loading={clonePending}
          onClick={() => onClone(item.id)}
          variant="ghost"
        >
          Clone to Workspace
        </Button>
      </td>
    </tr>
  );
}
