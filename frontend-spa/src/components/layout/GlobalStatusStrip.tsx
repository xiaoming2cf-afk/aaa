import { Badge } from "../ui";
import type { Team, Workspace } from "./types";

type GlobalStatusStripProps = {
  currentWorkspace?: Workspace;
  currentTeam?: Team;
};

export function GlobalStatusStrip({
  currentWorkspace,
  currentTeam,
}: GlobalStatusStripProps): JSX.Element {
  return (
    <section className="ops-status-ribbon" aria-label="Global research operations status">
      <div className="ops-status-item ops-status-item-live">
        <span className="ops-status-dot" aria-hidden="true" />
        <div>
          <strong>Authenticated</strong>
          <span>Session is active</span>
        </div>
      </div>
      <div className="ops-status-item">
        <strong>{currentWorkspace?.name || "Loading workspace"}</strong>
        <span>{currentTeam?.role || "Scoped team context"}</span>
      </div>
      <div className="ops-status-arbiter">
        <Badge tone="info">ARBITER shadow</Badge>
        <span>Active overrides require calibration gates</span>
      </div>
    </section>
  );
}
