import { Badge, Surface } from "../ui";

export function LibraryBoundaryPanel({
  currentTeamName,
  teamId,
  workspaceId,
}: {
  currentTeamName?: string;
  teamId: string;
  workspaceId: string;
}): JSX.Element {
  return (
    <Surface
      actions={<Badge tone={teamId ? "info" : "warning"}>{teamId ? "Team selected" : "No team"}</Badge>}
      eyebrow="Library Rules"
      span
      title="Publication Boundary"
      tone="muted"
    >
      <div className="detail-grid">
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Read-only library</strong>
            <span>{currentTeamName || "No team"}</span>
          </div>
          <p className="muted">Published artifacts are not edited in place from this page.</p>
        </div>
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Workspace clone target</strong>
            <span>{workspaceId || "none"}</span>
          </div>
          <p className="muted">Clone to Workspace keeps source metadata so the copied knowledge record can be reviewed again.</p>
        </div>
      </div>
    </Surface>
  );
}
