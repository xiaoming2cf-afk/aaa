import type { Team, Workspace } from "./types";

type ScopePanelProps = {
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  onWorkspaceChange: (value: string) => void;
  teamId: string;
  onTeamChange: (value: string) => void;
};

export function ScopePanel({
  workspaces,
  teams,
  workspaceId,
  onWorkspaceChange,
  teamId,
  onTeamChange,
}: ScopePanelProps): JSX.Element {
  return (
    <div className="ops-scope-panel" aria-label="Workspace and team scope">
      <label className="ops-field">
        <span>Workspace</span>
        <select value={workspaceId} onChange={(event) => onWorkspaceChange(event.target.value)}>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
          ))}
        </select>
      </label>
      <label className="ops-field">
        <span>Team</span>
        <select value={teamId} onChange={(event) => onTeamChange(event.target.value)}>
          <option value="">No team</option>
          {teams.map((team) => (
            <option key={team.id} value={team.id}>{team.name}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
