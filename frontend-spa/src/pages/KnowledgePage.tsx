import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";
import { KnowledgeCreatePanel } from "../components/knowledge/KnowledgeCreatePanel";
import { KnowledgeGatePanel } from "../components/knowledge/KnowledgeGatePanel";
import { KnowledgeRecordsPanel } from "../components/knowledge/KnowledgeRecordsPanel";
import type { KnowledgeRecord } from "../components/knowledge/types";

type UseAppState = () => {
  workspaceId: string;
  teamId: string;
  teams: Array<{ id: string; name: string }>;
};

export function KnowledgePage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId, teamId, teams } = useAppState();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const knowledgeQuery = useQuery({
    queryKey: ["knowledge", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: KnowledgeRecord[] }>(`/api/workspaces/${workspaceId}/knowledge`),
  });

  const createMutation = useMutation({
    mutationFn: () => apiFetch(`/api/workspaces/${workspaceId}/knowledge`, {
      method: "POST",
      body: JSON.stringify({
        title,
        content,
        tags: [],
        metadata: { source_type: "workspace_note", source: "spa" },
      }),
    }),
    onSuccess: () => {
      setTitle("");
      setContent("");
      void queryClient.invalidateQueries({ queryKey: ["knowledge", workspaceId] });
    },
  });

  const publishMutation = useMutation({
    mutationFn: (recordId: string) => apiFetch(`/api/workspaces/${workspaceId}/knowledge/${recordId}/publish`, {
      method: "POST",
      body: JSON.stringify({ team_id: teamId }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["team-library", teamId] });
    },
  });

  const records = knowledgeQuery.data?.items || [];
  const readyCount = useMemo(() => records.filter((item) => item.publish_allowed).length, [records]);
  const blockedCount = records.length - readyCount;
  const currentTeam = useMemo(() => teams.find((team) => team.id === teamId), [teamId, teams]);

  return (
    <div className="terminal-page workbench-knowledge">
      <KnowledgeCreatePanel
        content={content}
        disabled={!workspaceId || !title || !content}
        error={createMutation.isError ? createMutation.error as Error : null}
        isPending={createMutation.isPending}
        onContentChange={setContent}
        onSave={() => createMutation.mutate()}
        onTitleChange={setTitle}
        title={title}
      />
      <KnowledgeRecordsPanel
        blockedCount={blockedCount}
        isError={knowledgeQuery.isError}
        isLoading={knowledgeQuery.isLoading}
        isSuccess={knowledgeQuery.isSuccess}
        onPublish={(recordId) => publishMutation.mutate(recordId)}
        onRetry={() => void knowledgeQuery.refetch()}
        publishError={publishMutation.isError ? publishMutation.error as Error : null}
        publishing={publishMutation.isPending}
        readyCount={readyCount}
        records={records}
        teamId={teamId}
        teamName={currentTeam?.name}
      />
      <KnowledgeGatePanel teamId={teamId} workspaceId={workspaceId} />
    </div>
  );
}
