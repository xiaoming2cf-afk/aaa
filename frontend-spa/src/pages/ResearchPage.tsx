import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";

type UseAppState = () => {
  workspaceId: string;
  teamId: string;
  setTeamId: (value: string) => void;
  teams: Array<{ id: string; name: string }>;
};

type RunSummary = {
  id: string;
  topic: string;
  status: string;
  current_stage: string;
  queue_status: string;
  review_summary: string;
  quality_summary?: { quality_score?: number };
  publish_allowed?: boolean;
  blocking_reasons?: string[];
  delivery_review?: {
    deliverable?: boolean;
    publish_allowed?: boolean;
    blocking_reasons?: string[];
  };
};

type ResearchRuntimeCapability = {
  research_runtime: {
    enabled: boolean;
    code: string;
    message: string;
    trace?: Record<string, unknown>;
  };
};

export function ResearchPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId, teamId, setTeamId, teams } = useAppState();
  const queryClient = useQueryClient();
  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState("");
  const [instructions, setInstructions] = useState("");
  const [mode, setMode] = useState("standard");
  const [draftVariants, setDraftVariants] = useState("1");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [retryInstructions, setRetryInstructions] = useState("");

  const runsQuery = useQuery({
    queryKey: ["research-runs", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: RunSummary[] }>(`/api/workspaces/${workspaceId}/research/runs`),
    refetchInterval: (query) => {
      const items = (query.state.data as { items?: RunSummary[] } | undefined)?.items || [];
      return items.some((item) => !["saved", "blocked", "failed"].includes(item.status)) ? 5000 : false;
    },
  });

  const selectedRunQuery = useQuery({
    queryKey: ["research-run-detail", workspaceId, selectedRunId],
    enabled: Boolean(workspaceId && selectedRunId),
    queryFn: () => apiFetch<{ run: any; eval_candidate?: any }>(`/api/workspaces/${workspaceId}/research/runs/${selectedRunId}`),
    refetchInterval: (query) => {
      const status = (query.state.data as { run?: { status?: string } } | undefined)?.run?.status;
      return status && !["saved", "blocked", "failed"].includes(status) ? 5000 : false;
    },
  });

  const qualityQuery = useQuery({
    queryKey: ["quality-scorecard", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<any>(`/api/workspaces/${workspaceId}/quality/scorecard`),
  });

  const runtimeQuery = useQuery({
    queryKey: ["research-runtime", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<ResearchRuntimeCapability>(`/api/workspaces/${workspaceId}/research/runtime`),
  });

  const createRunMutation = useMutation({
    mutationFn: () => apiFetch(`/api/workspaces/${workspaceId}/research/runs`, {
      method: "POST",
      body: JSON.stringify({
        topic,
        question,
        instructions,
        asset_ids: [],
        draft_variants: Number(draftVariants || "1"),
        mode,
      }),
    }),
    onSuccess: (payload: any) => {
      setSelectedRunId(payload.run.id);
      void queryClient.invalidateQueries({ queryKey: ["research-runs", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["quality-scorecard", workspaceId] });
    },
  });

  const retryRunMutation = useMutation({
    mutationFn: () => apiFetch(`/api/workspaces/${workspaceId}/research/runs/${selectedRunId}/retry`, {
      method: "POST",
      body: JSON.stringify({
        instructions: retryInstructions,
        asset_ids: [],
        draft_variants: 1,
      }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-runs", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["research-run-detail", workspaceId, selectedRunId] });
    },
  });

  const publishRunMutation = useMutation({
    mutationFn: () => apiFetch(`/api/workspaces/${workspaceId}/research/runs/${selectedRunId}/publish`, {
      method: "POST",
      body: JSON.stringify({
        team_id: teamId,
      }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-runs", workspaceId] });
    },
  });

  const selectedRun = selectedRunQuery.data?.run;
  const publishAllowed = Boolean(selectedRun?.publish_allowed);
  const publishBlockers = (selectedRun?.blocking_reasons || selectedRun?.delivery_review?.blocking_reasons || []) as string[];
  const scoreSummary = useMemo(() => qualityQuery.data?.metrics || {}, [qualityQuery.data]);
  const candidateDrafts = (selectedRun?.candidate_drafts || []) as Array<any>;
  const arbiterMode = selectedRun?.metrics?.arbiter_math_mode || "off";
  const selectionTrace = selectedRun?.metrics?.arbiter_selection_v2 || {};
  const runtime = runtimeQuery.data?.research_runtime;
  const runtimeReady = runtime?.enabled === true;
  const runtimeStatus = runtimeQuery.isLoading
    ? "Checking research runtime availability."
    : runtimeQuery.isError
      ? "Research runtime status could not be verified; run creation is blocked."
      : runtimeReady
        ? "Research runtime is available."
        : runtime?.message || "Research generation is disabled in this deployment.";

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Launch</p>
            <h3>Research Run</h3>
            <p>{qualityQuery.data?.deliverable ? "Delivery gate passed." : "Delivery gate blocks publication until review reaches 100%."}</p>
          </div>
          <div className={qualityQuery.data?.deliverable ? "score-chip success" : "score-chip"}>{qualityQuery.data?.total_score || 0}/500</div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Topic</span>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Inflation persistence" />
          </label>
          <label className="field">
            <span>Question</span>
            <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What explains inflation persistence?" />
          </label>
          <label className="field field-span">
            <span>Instructions</span>
            <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={4} />
          </label>
          <label className="field">
            <span>Mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="standard">standard</option>
              <option value="deep_research">deep_research</option>
            </select>
          </label>
          <label className="field">
            <span>Draft Variants</span>
            <select value={draftVariants} onChange={(event) => setDraftVariants(event.target.value)}>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </label>
        </div>
        <div className="action-row">
          <button
            className="primary-button"
            type="button"
            disabled={!workspaceId || !topic || createRunMutation.isPending || !runtimeReady}
            onClick={() => createRunMutation.mutate()}
          >
            Start Run
          </button>
          <span className="muted">{createRunMutation.isError ? (createRunMutation.error as Error).message : runtimeStatus}</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Monitoring</p>
            <h3>Recent Runs</h3>
          </div>
        </div>
        <div className="list-stack">
          {(runsQuery.data?.items || []).map((item) => (
            <button key={item.id} className={selectedRunId === item.id ? "list-card selected" : "list-card"} type="button" onClick={() => setSelectedRunId(item.id)}>
              <div className="list-card-title">
                <strong>{item.topic}</strong>
                <span>{item.status}</span>
              </div>
              <p>{item.review_summary || item.current_stage}</p>
              <small>{item.queue_status}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Trace</p>
            <h3>Run Detail</h3>
          </div>
          <div className="inline-metrics">
            <span>Citation {scoreSummary.citation_coverage ?? "-"}</span>
            <span>Unsupported {scoreSummary.unsupported_claim_rate ?? "-"}</span>
            <span>Review Precision {scoreSummary.review_block_precision ?? "-"}</span>
          </div>
        </div>
        {selectedRun ? (
          <div className="detail-grid">
            <div className="detail-column">
              <h4>Evidence</h4>
              <pre>{JSON.stringify(selectedRun.evidence || {}, null, 2)}</pre>
              <h4>Review</h4>
              <pre>{JSON.stringify(selectedRun.review || {}, null, 2)}</pre>
              <h4>Delivery Review</h4>
              <pre>{JSON.stringify(selectedRun.delivery_review || {}, null, 2)}</pre>
            </div>
            <div className="detail-column">
              <h4>Trace</h4>
              <pre>{JSON.stringify(selectedRun.trace || [], null, 2)}</pre>
              <h4>ARBITER Candidates</h4>
              {selectionTrace?.comparison ? (
                <div className="list-card static-card">
                  <div className="list-card-title">
                    <strong>Selection v2</strong>
                    <span>{selectionTrace.mode || arbiterMode}</span>
                  </div>
                  <p>
                    baseline {selectionTrace.baseline_draft_id || "none"} / proposed {selectionTrace.proposed_draft_id || "none"} / chosen {selectionTrace.chosen_draft_id || "none"}
                  </p>
                  <small>
                    advantage {selectionTrace.comparison?.advantage ?? "-"} / margin {selectionTrace.comparison?.override_margin ?? "-"} / fallback {selectionTrace.comparison?.fallback_reason || "override_applied"}
                  </small>
                </div>
              ) : null}
              {candidateDrafts.length ? (
                <div className="list-stack">
                  {candidateDrafts.map((candidate) => {
                    const arbiter = candidate?.metadata?.arbiter || {};
                    const v2 = arbiter.v2 || {};
                    return (
                      <div key={candidate.draft_id} className="list-card static-card">
                        <div className="list-card-title">
                          <strong>{candidate.draft_id}</strong>
                          <span>{candidate.status}</span>
                        </div>
                        <p>{candidate.summary || "No reviewer summary."}</p>
                        <small>
                          mode {arbiter.mode || arbiterMode} / baseline score {arbiter.baseline_score ?? candidate.score ?? "-"} / baseline utility {arbiter.utility ?? "-"} / v2 utility {v2.utility ?? "-"} / revision cost {v2.revision_cost ?? "-"} / risk {arbiter.risk ?? "-"}
                        </small>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="muted">No candidate-level ARBITER traces were persisted for this run.</p>
              )}
              <h4>Final Report</h4>
              <pre>{selectedRun.final_text || ""}</pre>
            </div>
          </div>
        ) : (
          <p className="muted">Select a run to inspect evidence, review, trace, and final report.</p>
        )}
        {selectedRun && (
          <div className="action-row">
            <label className="field field-span">
              <span>Retry Instructions</span>
              <textarea value={retryInstructions} onChange={(event) => setRetryInstructions(event.target.value)} rows={3} />
            </label>
            <button className="ghost-button" type="button" disabled={!selectedRunId || retryRunMutation.isPending} onClick={() => retryRunMutation.mutate()}>
              Retry Writer/Reviewer
            </button>
            <select value={teamId} disabled={!teams.length} onChange={(event) => setTeamId(event.target.value)}>
              <option value="">{teams.length ? "Select team" : "No team"}</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
              ))}
            </select>
            <button
              className="primary-button"
              type="button"
              disabled={!teamId || publishRunMutation.isPending || !selectedRunId || !publishAllowed}
              onClick={() => publishRunMutation.mutate()}
            >
              Publish to Team Library
            </button>
          </div>
        )}
        {selectedRun && !publishAllowed ? (
          <div className="list-card static-card">
            <strong>Publish is blocked</strong>
            <p>{publishBlockers[0] || "The delivery review has not yet reached 100%."}</p>
          </div>
        ) : null}
        {publishRunMutation.isError ? (
          <div className="list-card static-card">
            <strong>Publish failed</strong>
            <p>{(publishRunMutation.error as Error).message}</p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
