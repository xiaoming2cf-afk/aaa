import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";
import {
  LiveRunQueue,
  RunComposer,
  RunDetailPanel,
  type ResearchRuntimeCapability,
  type RunDetail,
  type RunDetailTab,
  type RunSummary,
} from "../components/research";

type UseAppState = () => {
  workspaceId: string;
  teamId: string;
  setTeamId: (value: string) => void;
  teams: Array<{ id: string; name: string }>;
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
  const [detailTab, setDetailTab] = useState<RunDetailTab>("overview");

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
    queryFn: () => apiFetch<{ run: RunDetail; eval_candidate?: any }>(`/api/workspaces/${workspaceId}/research/runs/${selectedRunId}`),
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
  const publishGate = selectedRun
    ? selectedRun.publish_allowed === true
      ? true
      : selectedRun.publish_allowed === false
        ? false
        : selectedRun.delivery_review?.publish_allowed
    : undefined;
  const publishAllowed = publishGate === true;
  const publishBlockers = (selectedRun?.blocking_reasons || selectedRun?.delivery_review?.blocking_reasons || []) as string[];
  const scoreSummary = useMemo(() => qualityQuery.data?.metrics || {}, [qualityQuery.data]);
  const candidateDrafts = (selectedRun?.candidate_drafts || []) as Array<any>;
  const arbiterMode = selectedRun?.metrics?.arbiter_math_mode || "off";
  const selectionTrace = (selectedRun?.metrics?.arbiter_selection_v2 || {}) as any;
  const runtime = runtimeQuery.data?.research_runtime;
  const runtimeReady = runtime?.enabled === true;
  const runtimeStatus = runtimeQuery.isLoading
    ? "Checking research runtime availability."
    : runtimeQuery.isError
      ? "Research runtime status could not be verified; run creation is blocked."
      : runtimeReady
        ? "Research runtime is available."
        : runtime?.message || "Research generation is disabled in this deployment.";
  const runtimeDisabled = !runtimeQuery.isLoading && !runtimeReady;
  const runtimeTone = runtimeQuery.isLoading ? "warning" : runtimeReady ? "success" : "danger";
  const runtimeLabel = runtimeQuery.isLoading ? "Checking" : runtimeReady ? "Ready" : "Unavailable";
  const qualityReady = qualityQuery.isSuccess && Boolean(qualityQuery.data);
  const workspaceDeliverable = qualityReady ? qualityQuery.data?.deliverable === true : undefined;
  const workspaceScoreLabel = qualityReady
    ? `${qualityQuery.data?.total_score ?? 0}/500`
    : qualityQuery.isLoading
      ? "Checking"
      : "Unavailable";
  const runItems = runsQuery.data?.items || [];

  return (
    <div className="terminal-page workbench-research">
      <RunComposer
        createErrorMessage={createRunMutation.isError ? (createRunMutation.error as Error).message : undefined}
        createPending={createRunMutation.isPending}
        draftVariants={draftVariants}
        instructions={instructions}
        mode={mode}
        onDraftVariantsChange={setDraftVariants}
        onInstructionsChange={setInstructions}
        onModeChange={setMode}
        onQuestionChange={setQuestion}
        onStart={() => createRunMutation.mutate()}
        onTopicChange={setTopic}
        question={question}
        runtimeCode={runtime?.code}
        runtimeDisabled={runtimeDisabled}
        runtimeLabel={runtimeLabel}
        runtimeReady={runtimeReady}
        runtimeStatus={runtimeStatus}
        runtimeTone={runtimeTone}
        topic={topic}
        workspaceDeliverable={workspaceDeliverable}
        workspaceId={workspaceId}
        workspaceScoreLabel={workspaceScoreLabel}
      />

      <LiveRunQueue
        errorMessage={runsQuery.isError ? (runsQuery.error as Error).message : undefined}
        isError={runsQuery.isError}
        isSuccess={runsQuery.isSuccess}
        onSelectRun={setSelectedRunId}
        runs={runItems}
        selectedRunId={selectedRunId}
      />

      <RunDetailPanel
        arbiterMode={arbiterMode}
        candidateDrafts={candidateDrafts}
        detailErrorMessage={selectedRunQuery.isError ? (selectedRunQuery.error as Error).message : undefined}
        detailTab={detailTab}
        onDetailTabChange={setDetailTab}
        onPublish={() => publishRunMutation.mutate()}
        onRetry={() => retryRunMutation.mutate()}
        onRetryInstructionsChange={setRetryInstructions}
        onTeamChange={setTeamId}
        publishAllowed={publishAllowed}
        publishBlockers={publishBlockers}
        publishErrorMessage={publishRunMutation.isError ? (publishRunMutation.error as Error).message : undefined}
        publishGate={publishGate}
        publishPending={publishRunMutation.isPending}
        retryErrorMessage={retryRunMutation.isError ? (retryRunMutation.error as Error).message : undefined}
        retryInstructions={retryInstructions}
        retryPending={retryRunMutation.isPending}
        scoreSummary={scoreSummary}
        selectedRun={selectedRun}
        selectedRunId={selectedRunId}
        selectionTrace={selectionTrace}
        teamId={teamId}
        teams={teams}
      />
    </div>
  );
}
