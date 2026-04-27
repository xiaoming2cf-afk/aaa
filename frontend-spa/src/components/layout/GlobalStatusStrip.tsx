import { Badge, MetricPill } from "../ui";
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
    <section className="metric-strip" aria-label="Global research operations status">
      <MetricPill label="Session" value="Authenticated" tone="success" />
      <MetricPill label="Workspace" value={currentWorkspace?.name || "Loading"} />
      <MetricPill label="Team" value={currentTeam?.role || "Scoped"} />
      <span className="ops-global-state">
        <Badge tone="info">ARBITER shadow</Badge>
        <span>Active overrides require calibration gates</span>
      </span>
    </section>
  );
}
