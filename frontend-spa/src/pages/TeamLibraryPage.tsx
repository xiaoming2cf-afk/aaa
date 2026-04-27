import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";
import {
  LibraryBoundaryPanel,
  TeamArtifactsPanel,
  TeamSelectorPanel,
  type TeamLibraryRecord,
} from "../components/team-library";

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
    queryFn: () => apiFetch<{ items: TeamLibraryRecord[] }>(`/api/teams/${teamId}/library`),
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

  const currentTeam = useMemo(() => teams.find((team) => team.id === teamId), [teamId, teams]);
  const libraryItems = libraryQuery.data?.items || [];

  return (
    <div className="terminal-page workbench-library">
      <TeamSelectorPanel
        createError={createTeamMutation.isError ? createTeamMutation.error as Error : null}
        createPending={createTeamMutation.isPending}
        onCreateTeam={() => createTeamMutation.mutate()}
        onDescriptionChange={setTeamDescription}
        onTeamChange={setTeamId}
        onTeamNameChange={setTeamName}
        teamDescription={teamDescription}
        teamId={teamId}
        teamName={teamName}
        teams={teams}
      />
      <TeamArtifactsPanel
        cloneError={cloneMutation.isError ? cloneMutation.error as Error : null}
        clonePending={cloneMutation.isPending}
        currentTeamName={currentTeam?.name}
        isError={libraryQuery.isError}
        isLoading={libraryQuery.isLoading}
        isSuccess={libraryQuery.isSuccess}
        items={libraryItems}
        onClone={(recordId) => cloneMutation.mutate(recordId)}
        onRetry={() => void libraryQuery.refetch()}
        teamId={teamId}
        teamsCount={teams.length}
        workspaceId={workspaceId}
      />
      <LibraryBoundaryPanel currentTeamName={currentTeam?.name} teamId={teamId} workspaceId={workspaceId} />
    </div>
  );
}
