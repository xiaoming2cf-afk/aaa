import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import {
  ComposerPanel,
  DataLabIdeLayout,
  DatasetContextPanel,
  InspectorTabsPanel,
  LlmConfigPanel,
  MessageTimelinePanel,
  NotebookExportPanel,
  SessionHistoryPanel,
  SessionLaunchPanel,
  TracePanel,
} from "../components/data-lab";
import {
  EMPTY_LLM_FORM,
  artifactLabelFromPath,
  humanInterventionRequired,
  llmResolvedStatus,
  workspaceFormState,
} from "../components/data-lab/helpers";
import type {
  AgentSession,
  AssetSummary,
  HistoryItem,
  LlmConfig,
  LlmFormState,
  NotebookResponse,
  ReportResponse,
  SendMessageInput,
} from "../components/data-lab/types";

type UseAppState = () => {
  workspaceId: string;
};

export function DataLabAgentPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("Data Lab Agent Session");
  const [assetId, setAssetId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [message, setMessage] = useState("Show a concise overview of this dataset.");
  const [manualCode, setManualCode] = useState("");
  const [interventionNote, setInterventionNote] = useState("");
  const [executionMode, setExecutionMode] = useState("");
  const [llmForm, setLlmForm] = useState<LlmFormState>({ ...EMPTY_LLM_FORM });
  const [llmHydratedWorkspaceId, setLlmHydratedWorkspaceId] = useState("");
  const [llmTestResult, setLlmTestResult] = useState("");
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [preparedNotebookDownloadPath, setPreparedNotebookDownloadPath] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);
  const datasetSelectRef = useRef<HTMLSelectElement>(null);
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const manualCodeInputRef = useRef<HTMLTextAreaElement>(null);
  const interventionNoteInputRef = useRef<HTMLInputElement>(null);
  const executionModeSelectRef = useRef<HTMLSelectElement>(null);

  const runFromQuery = useMemo(() => new URLSearchParams(location.search).get("run") || "", [location.search]);

  const assetsQuery = useQuery({
    queryKey: ["assets", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: AssetSummary[] }>(`/api/workspaces/${workspaceId}/assets`),
  });

  const historyQuery = useQuery({
    queryKey: ["data-lab-history", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ agent_sessions?: HistoryItem[] }>(`/api/workspaces/${workspaceId}/data-lab/history`),
  });

  const llmConfigQuery = useQuery({
    queryKey: ["data-lab-agent-llm-config", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<LlmConfig>(`/api/workspaces/${workspaceId}/data-lab/agent/llm-config`),
  });

  const sessionQuery = useQuery({
    queryKey: ["data-lab-agent-session", workspaceId, selectedRunId],
    enabled: Boolean(workspaceId && selectedRunId),
    queryFn: () => apiFetch<{ session: AgentSession }>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}`),
  });

  const datasetAssets = useMemo(
    () => (assetsQuery.data?.items || []).filter((asset) => asset.kind.startsWith("dataset_")),
    [assetsQuery.data],
  );

  useEffect(() => {
    setSelectedRunId(runFromQuery || "");
    setAssetId("");
    setReportMarkdown("");
    setLlmTestResult("");
    setLlmForm({ ...EMPTY_LLM_FORM });
    setLlmHydratedWorkspaceId("");
    setPreparedNotebookDownloadPath("");
  }, [workspaceId, runFromQuery]);

  useEffect(() => {
    if (assetId && datasetAssets.some((asset) => asset.id === assetId)) {
      return;
    }
    if (datasetAssets.length) {
      setAssetId(datasetAssets[0].id);
    }
  }, [assetId, datasetAssets]);

  useEffect(() => {
    if (runFromQuery) {
      if (selectedRunId !== runFromQuery) {
        setSelectedRunId(runFromQuery);
      }
      return;
    }
    const firstSession = historyQuery.data?.agent_sessions?.[0];
    if (!selectedRunId && firstSession) {
      setSelectedRunId(firstSession.run_id || firstSession.id);
    }
  }, [historyQuery.data, runFromQuery, selectedRunId]);

  useEffect(() => {
    const workspace = llmConfigQuery.data?.workspace;
    if (!workspaceId || !workspace || llmHydratedWorkspaceId === workspaceId) {
      return;
    }
    setLlmForm(workspaceFormState(workspace));
    setLlmHydratedWorkspaceId(workspaceId);
  }, [llmConfigQuery.data, llmHydratedWorkspaceId, workspaceId]);

  useEffect(() => {
    setReportMarkdown("");
    setPreparedNotebookDownloadPath("");
  }, [selectedRunId]);

  const createSessionMutation = useMutation({
    mutationFn: (payload: { nextTitle: string; nextAssetId: string }) => apiFetch<{ session: AgentSession }>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions`, {
      method: "POST",
      body: JSON.stringify({
        title: payload.nextTitle,
        language: "Chinese",
        asset_ids: [payload.nextAssetId],
      }),
    }),
    onSuccess: (payload) => {
      setSelectedRunId(payload.session.run_id);
      setReportMarkdown("");
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const saveLlmConfigMutation = useMutation({
    mutationFn: () => apiFetch<LlmConfig>(`/api/workspaces/${workspaceId}/data-lab/agent/llm-config`, {
      method: "PUT",
      body: JSON.stringify(llmForm),
    }),
    onSuccess: () => {
      setLlmForm((current) => ({ ...current, api_key: "", clear_api_key: false }));
      setLlmHydratedWorkspaceId("");
      setLlmTestResult("");
      void queryClient.invalidateQueries({ queryKey: ["data-lab-agent-llm-config", workspaceId] });
    },
  });

  const testLlmConfigMutation = useMutation({
    mutationFn: () => apiFetch<{ status: string; preview?: string; reason?: string }>(`/api/workspaces/${workspaceId}/data-lab/agent/llm-config/test`, {
      method: "POST",
    }),
    onSuccess: (payload) => {
      setLlmTestResult(`${payload.status}: ${payload.preview || payload.reason || ""}`);
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: (payload: SendMessageInput) => apiFetch<{ session: AgentSession }>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        message: payload.message,
        user_code: payload.userCode,
        intervention_note: payload.interventionNote,
        execution_mode: payload.executionMode,
      }),
    }),
    onSuccess: (_payload, variables) => {
      const currentManualCode = manualCodeInputRef.current?.value ?? "";
      const currentInterventionNote = interventionNoteInputRef.current?.value ?? "";
      if (currentManualCode === variables.userCode) {
        setManualCode("");
      }
      if (currentInterventionNote === variables.interventionNote) {
        setInterventionNote("");
      }
      void queryClient.invalidateQueries({ queryKey: ["data-lab-agent-session", workspaceId, selectedRunId] });
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const reportMutation = useMutation({
    mutationFn: () => apiFetch<ReportResponse>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/report`, {
      method: "POST",
    }),
    onSuccess: (payload) => {
      setReportMarkdown(payload.report.markdown);
      void queryClient.invalidateQueries({ queryKey: ["data-lab-agent-session", workspaceId, selectedRunId] });
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const notebookMutation = useMutation({
    mutationFn: () => apiFetch<NotebookResponse>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/notebook`, {
      method: "POST",
    }),
    onSuccess: (payload) => {
      queryClient.setQueryData(["data-lab-agent-session", workspaceId, selectedRunId], { session: payload.session });
      setPreparedNotebookDownloadPath(payload.notebook.download_path || "");
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const currentSession = sessionQuery.data?.session;
  const messages = currentSession?.messages || [];
  const firstAsset = currentSession?.assets?.[0];
  const firstProfile = firstAsset?.profile;
  const previewColumns = useMemo(() => {
    const declaredColumns = firstProfile?.column_names?.slice(0, 6) || [];
    if (declaredColumns.length) {
      return declaredColumns;
    }
    return Object.keys(firstProfile?.preview_rows?.[0] || {}).slice(0, 6);
  }, [firstProfile]);
  const latestAssistant = [...messages].reverse().find((item) => item.role === "assistant");
  const latestAssistantWithCode = [...messages].reverse().find((item) => item.role === "assistant" && item.code);
  const latestUser = [...messages].reverse().find((item) => item.role === "user");
  const needsHuman = currentSession?.run_status === "needs_human_intervention" || humanInterventionRequired(latestAssistantWithCode);
  const fallbackNotebookHref = selectedRunId && currentSession?.notebook_path ? `/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/notebook` : "";
  const notebookHref = preparedNotebookDownloadPath || fallbackNotebookHref;
  const notebookExportState = notebookHref
    ? "READY"
    : notebookMutation.isPending
      ? "PREPARING"
      : selectedRunId
        ? "NOT PREPARED"
        : "NO SESSION";
  const notebookExportMessage = notebookHref
    ? "Notebook download is ready."
    : notebookMutation.isPending
      ? "Preparing notebook export."
      : selectedRunId
        ? "Notebook download is not prepared."
        : "Select a session before preparing a notebook export.";
  const notebookExportSource = preparedNotebookDownloadPath
    ? "fresh export"
    : fallbackNotebookHref
      ? "session artifact"
      : "awaiting export";
  const notebookArtifactLabel = artifactLabelFromPath(currentSession?.notebook_path);
  const permalinkHref = currentSession?.detail_path || (selectedRunId ? `/app/data-lab-agent?run=${selectedRunId}` : "");
  const latestPrompt = latestUser?.content || message;
  const mutationError = createSessionMutation.error
    || sendMessageMutation.error
    || reportMutation.error
    || notebookMutation.error
    || saveLlmConfigMutation.error
    || testLlmConfigMutation.error;
  const sessionStatus = currentSession?.run_status || (sessionQuery.isFetching ? "loading" : selectedRunId ? "unknown" : "no session");
  const llmStatus = llmResolvedStatus(llmConfigQuery);
  const workspaceLlmStatus = llmConfigQuery.data?.workspace.configured
    ? llmConfigQuery.data.workspace.enabled
      ? "configured"
      : "disabled"
    : "unset";
  const environmentLlmStatus = llmConfigQuery.data?.environment.ready
    ? "ready"
    : llmConfigQuery.data?.environment.enabled
      ? "not ready"
      : "fallback";
  const currentExecutorMode = currentSession?.executor?.active_mode || currentSession?.executor?.requested_mode || "not run";

  const runMessage = (): void => {
    const payload = {
      message: messageInputRef.current?.value ?? message,
      userCode: manualCodeInputRef.current?.value ?? manualCode,
      interventionNote: interventionNoteInputRef.current?.value ?? interventionNote,
      executionMode: executionModeSelectRef.current?.value ?? executionMode,
    };
    setMessage(payload.message);
    setManualCode(payload.userCode);
    setInterventionNote(payload.interventionNote);
    setExecutionMode(payload.executionMode);
    sendMessageMutation.mutate(payload);
  };

  const retryLatestPrompt = (): void => {
    if (!latestPrompt) {
      return;
    }
    setMessage(latestPrompt);
    setManualCode("");
    setInterventionNote("Retry after previous failure.");
    sendMessageMutation.mutate({
      message: latestPrompt,
      userCode: "",
      interventionNote: "Retry after previous failure.",
      executionMode,
    });
  };

  const loadWorkspaceConfig = (): void => {
    setLlmForm(workspaceFormState(llmConfigQuery.data?.workspace));
  };

  return (
    <DataLabIdeLayout
      browser={(
        <>
          <SessionLaunchPanel
            assetId={assetId}
            assetsError={assetsQuery.isError ? (assetsQuery.error as Error) : null}
            assetsSuccess={assetsQuery.isSuccess}
            createPending={createSessionMutation.isPending}
            datasetAssets={datasetAssets}
            datasetSelectRef={datasetSelectRef}
            onCreateSession={(payload) => createSessionMutation.mutate(payload)}
            permalinkHref={permalinkHref}
            setAssetId={setAssetId}
            setTitle={setTitle}
            title={title}
            titleInputRef={titleInputRef}
            workspaceId={workspaceId}
          />
          <SessionHistoryPanel
            historyError={historyQuery.isError ? (historyQuery.error as Error) : null}
            historyItems={historyQuery.data?.agent_sessions || []}
            historySuccess={historyQuery.isSuccess}
            selectedRunId={selectedRunId}
            setSelectedRunId={setSelectedRunId}
          />
          <LlmConfigPanel
            environmentLlmStatus={environmentLlmStatus}
            error={llmConfigQuery.isError ? (llmConfigQuery.error as Error) : null}
            isError={llmConfigQuery.isError}
            llmConfig={llmConfigQuery.data}
            llmForm={llmForm}
            llmStatus={llmStatus}
            llmTestResult={llmTestResult}
            onLoadStored={loadWorkspaceConfig}
            onSave={() => saveLlmConfigMutation.mutate()}
            onTest={() => testLlmConfigMutation.mutate()}
            savePending={saveLlmConfigMutation.isPending}
            setLlmForm={setLlmForm}
            testPending={testLlmConfigMutation.isPending}
            workspaceId={workspaceId}
            workspaceLlmStatus={workspaceLlmStatus}
          />
        </>
      )}
      workspace={(
        <>
          <MessageTimelinePanel
            currentSession={currentSession}
            messages={messages}
            mutationError={mutationError ? (mutationError as Error) : null}
            sessionError={sessionQuery.isError ? (sessionQuery.error as Error) : null}
            sessionStatus={sessionStatus}
          />
          <ComposerPanel
            executionMode={executionMode}
            executionModeSelectRef={executionModeSelectRef}
            interventionNote={interventionNote}
            interventionNoteInputRef={interventionNoteInputRef}
            latestAssistantWithCode={latestAssistantWithCode}
            latestPrompt={latestPrompt}
            manualCode={manualCode}
            manualCodeInputRef={manualCodeInputRef}
            message={message}
            messageInputRef={messageInputRef}
            needsHuman={needsHuman}
            onGenerateReport={() => reportMutation.mutate()}
            onRetryLatestPrompt={retryLatestPrompt}
            onRunMessage={runMessage}
            reportPending={reportMutation.isPending}
            selectedRunId={selectedRunId}
            sendPending={sendMessageMutation.isPending}
            setExecutionMode={setExecutionMode}
            setInterventionNote={setInterventionNote}
            setManualCode={setManualCode}
            setMessage={setMessage}
          />
        </>
      )}
      inspector={(
        <InspectorTabsPanel
          dataset={<DatasetContextPanel firstAsset={firstAsset} firstProfile={firstProfile} previewColumns={previewColumns} />}
          notebook={(
            <NotebookExportPanel
              currentSessionReady={Boolean(currentSession)}
              notebookArtifactLabel={notebookArtifactLabel}
              notebookExportMessage={notebookExportMessage}
              notebookExportSource={notebookExportSource}
              notebookExportState={notebookExportState}
              notebookHref={notebookHref}
              notebookPending={notebookMutation.isPending}
              onPrepareNotebook={() => notebookMutation.mutate()}
              permalinkHref={permalinkHref}
              selectedRunId={selectedRunId}
            />
          )}
          trace={(
            <TracePanel
              currentExecutorMode={currentExecutorMode}
              currentSession={currentSession}
              latestAssistant={latestAssistant}
              reportMarkdown={reportMarkdown}
              sessionStatus={sessionStatus}
            />
          )}
        />
      )}
    />
  );
}
