import { Badge, Surface } from "../ui";

export function KnowledgeGatePanel({
  teamId,
  workspaceId,
}: {
  teamId: string;
  workspaceId: string;
}): JSX.Element {
  return (
    <Surface
      actions={<Badge tone={workspaceId ? "info" : "warning"}>{workspaceId ? "Workspace active" : "No workspace"}</Badge>}
      eyebrow="Publishing Control"
      span
      title="Review Gate"
      tone="muted"
    >
      <div className="detail-grid">
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Current workspace</strong>
            <span>{workspaceId || "none"}</span>
          </div>
          <p className="muted">Records stay in workspace scope until the delivery review allows publication.</p>
        </div>
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Team target</strong>
            <span>{teamId ? teamId.slice(0, 8) : "none"}</span>
          </div>
          <p className="muted">Select the active team in the shared app scope before publishing to the Team Library.</p>
        </div>
      </div>
    </Surface>
  );
}
