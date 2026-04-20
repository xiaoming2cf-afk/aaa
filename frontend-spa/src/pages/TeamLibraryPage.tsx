import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";

type UseAppState = () => {
  workspaceId: string;
  teamId: string;
  setTeamId: (value: string) => void;
  teams: Array<{ id: string; name: string }>;
  refreshShared: () => void;
};

export function TeamLibraryPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId, teamId, setTeamId, teams, refreshShared } = useAppState();
  const queryClient = useQueryClient();
  const [teamName, setTeamName] = useState("");
  const [teamDescription, setTeamDescription] = useState("");

  const libraryQuery = useQuery({
    queryKey: ["team-library", teamId],
    enabled: Boolean(teamId),
    queryFn: () => apiFetch<{ items: any[] }>(`/api/teams/${teamId}/library`),
  });

  const createTeamMutation = useMutation({
    mutationFn: () => apiFetch<{ team: { id: string } }>("/api/teams", {
      method: "POST",
      body: JSON.stringify({ name: teamName, description: teamDescription }),
    }),
    onSuccess: (payload) => {
      setTeamId(payload.team.id);
      refreshShared();
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: (recordId: string) => apiFetch(`/api/teams/${teamId}/library/${recordId}/clone`, {
      method: "POST",
      body: JSON.stringify({
        workspace_id: workspaceId,
        title: "",
        include_source_metadata: true,
      }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge", workspaceId] });
    },
  });

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Team Model</p>
            <h3>Create or Select Team</h3>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Current Team</span>
            <select value={teamId} onChange={(event) => setTeamId(event.target.value)}>
              <option value="">No team</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>New Team Name</span>
            <input value={teamName} onChange={(event) => setTeamName(event.target.value)} />
          </label>
          <label className="field field-span">
            <span>Description</span>
            <textarea value={teamDescription} onChange={(event) => setTeamDescription(event.target.value)} rows={3} />
          </label>
        </div>
        <div className="action-row">
          <button className="primary-button" type="button" disabled={!teamName || createTeamMutation.isPending} onClick={() => createTeamMutation.mutate()}>
            Create Team
          </button>
          <span className="muted">Publishing remains manual. Team library stays read-only until cloned back to a workspace.</span>
        </div>
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Published Artifacts</p>
            <h3>Team Library</h3>
          </div>
        </div>
        {!teamId ? (
          <p className="muted">Choose or create a team to browse published records.</p>
        ) : (
          <div className="list-stack">
            {(libraryQuery.data?.items || []).map((item) => (
              <div key={item.id} className="list-card static-card">
                <div className="list-card-title">
                  <strong>{item.title}</strong>
                  <span>{item.source_type}</span>
                </div>
                <p>{item.summary}</p>
                <pre>{JSON.stringify(item.metadata || {}, null, 2)}</pre>
                <div className="action-row">
                  <button className="ghost-button" type="button" disabled={!workspaceId || cloneMutation.isPending} onClick={() => cloneMutation.mutate(item.id)}>
                    Clone to Workspace
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
