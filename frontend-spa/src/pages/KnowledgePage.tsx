import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";

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
    queryFn: () => apiFetch<{ items: any[] }>(`/api/workspaces/${workspaceId}/knowledge`),
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
    },
  });

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Workspace Notes</p>
            <h3>Create Knowledge Record</h3>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field field-span">
            <span>Content</span>
            <textarea value={content} onChange={(event) => setContent(event.target.value)} rows={8} />
          </label>
        </div>
        <div className="action-row">
          <button className="primary-button" type="button" disabled={!workspaceId || !title || !content || createMutation.isPending} onClick={() => createMutation.mutate()}>
            Save Knowledge
          </button>
          <span className="muted">Knowledge records can be published into the team library after review.</span>
        </div>
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Knowledge Base</p>
            <h3>Records</h3>
          </div>
        </div>
        <div className="list-stack">
          {(knowledgeQuery.data?.items || []).map((item) => (
            <div key={item.id} className="list-card static-card">
              <div className="list-card-title">
                <strong>{item.title}</strong>
                <span>{item.id.slice(0, 8)}</span>
              </div>
              <p>{item.content_excerpt || item.content || ""}</p>
              {!item.publish_allowed ? (
                <p className="muted">{(item.blocking_reasons || [])[0] || "Publish is blocked until delivery review reaches 100%."}</p>
              ) : (
                <p className="muted">Publish is allowed.</p>
              )}
              <div className="action-row">
                <select value={teamId} disabled={!teams.length} onChange={() => undefined}>
                  <option value="">{teams.length ? "Select team" : "No team"}</option>
                  {teams.map((team) => (
                    <option key={team.id} value={team.id}>{team.name}</option>
                  ))}
                </select>
                <button
                  className="ghost-button"
                  type="button"
                  disabled={!teamId || publishMutation.isPending || !item.publish_allowed}
                  onClick={() => publishMutation.mutate(item.id)}
                >
                  Publish
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
