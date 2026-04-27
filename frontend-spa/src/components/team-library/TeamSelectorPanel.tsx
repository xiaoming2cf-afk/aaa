import { Plus } from "lucide-react";
import { InlineErrorState } from "../StatusPrimitives";
import { Button, Field, Surface } from "../ui";

export function TeamSelectorPanel({
  createError,
  createPending,
  onCreateTeam,
  onDescriptionChange,
  onTeamChange,
  onTeamNameChange,
  teamDescription,
  teamId,
  teamName,
  teams,
}: {
  createError?: Error | null;
  createPending: boolean;
  onCreateTeam: () => void;
  onDescriptionChange: (value: string) => void;
  onTeamChange: (value: string) => void;
  onTeamNameChange: (value: string) => void;
  teamDescription: string;
  teamId: string;
  teamName: string;
  teams: Array<{ id: string; name: string }>;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-5"
      description="Choose the team whose published artifacts should be browsed, or create a new read-only publication target."
      eyebrow="Team Model"
      title="Create or Select Team"
      tone="emphasis"
    >
      <div className="form-grid">
        <Field label="Current Team">
          <select value={teamId} onChange={(event) => onTeamChange(event.target.value)}>
            <option value="">No team</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>{team.name}</option>
            ))}
          </select>
        </Field>
        <Field label="New Team Name">
          <input value={teamName} onChange={(event) => onTeamNameChange(event.target.value)} />
        </Field>
        <Field label="Description" span>
          <textarea value={teamDescription} onChange={(event) => onDescriptionChange(event.target.value)} rows={3} />
        </Field>
      </div>
      <div className="action-row">
        <Button
          disabled={!teamName}
          icon={<Plus />}
          loading={createPending}
          onClick={onCreateTeam}
          variant="primary"
        >
          Create Team
        </Button>
        <span className="muted">Publishing remains manual. Team library stays read-only until cloned back to a workspace.</span>
      </div>
      {createError ? (
        <InlineErrorState title="Team was not created" description={createError.message} />
      ) : null}
    </Surface>
  );
}
