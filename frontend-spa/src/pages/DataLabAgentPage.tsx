import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { InlineEmptyState, InlineErrorState } from "../components/StatusPrimitives";

type UseAppState = () => {
  workspaceId: string;
};

type AssetSummary = {
  id: string;
  title: string;
  kind: string;
};

type KnowledgeCard = {
  id: string;
  source_type: string;
  title: string;
  summary: string;
  score?: number;
  tags?: string[];
};

type AgentMessage = {
  id: string;
  role: string;
  content: string;
  status?: string;
  code?: string;
  user_code?: boolean;
  intervention_note?: string;
  execution_mode?: string;
  coder_source?: string;
  risk_notes?: string[];
  knowledge_cards?: KnowledgeCard[];
  llm_trace_summary?: Array<{
    role: string;
    source: string;
    summary?: string;
    fallback?: boolean;
    llm_error?: string;
  }>;
  human_intervention?: {
    required?: boolean;
    provided?: boolean;
    note?: string;
    reason?: string;
    next_action?: string;
  };
  artifact_manifest?: {
    count?: number;
    image_count?: number;
    total_size_bytes?: number;
    names?: string[];
  };
  profile_snapshot?: {
    rows?: number;
    columns?: number;
    schema_fingerprint?: string;
  };
  execution?: {
    stdout?: string;
    stderr?: string;
    error?: string;
    artifacts?: Array<{
      name: string;
      path: string;
      relative_path?: string;
      size_bytes?: number;
    }>;
  };
  repair_trace?: Array<{
    attempt: number;
    status: string;
    error: string;
    suggestion?: string;
    reviewer_source?: string;
    repair_strategy?: string;
  }>;
  math_trace?: {
    mode?: string;
    override_margin?: number;
    retrieval?: {
      candidate_count?: number;
      selected_count?: number;
      v2?: {
        comparison?: {
          baseline_choice?: string;
          proposed_choice?: string;
          chosen_choice?: string;
          advantage?: number;
          override_margin?: number;
          fallback_reason?: string;
        };
      };
    };
    repair_decisions?: Array<{
      best_action?: string;
      error_class?: string;
      v2?: {
        comparison?: {
          baseline_choice?: string;
          proposed_choice?: string;
          chosen_choice?: string;
          advantage?: number;
          override_margin?: number;
          fallback_reason?: string;
        };
      };
    }>;
    v2_state_summary?: {
      successful_cell_count?: number;
      safety_event_count?: number;
      recent_failure_classes?: string[];
      run_status?: string;
    };
  };
};

type AgentSession = {
  run_id: string;
  title: string;
  summary?: string;
  run_status?: string;
  detail_path?: string;
  report_path?: string;
  notebook_path?: string;
  updated_at?: string;
  executor?: {
    strategy?: string;
    requested_mode?: string;
    active_mode?: string;
    ipython_enabled?: boolean;
  };
  llm?: {
    enabled?: boolean;
    ready?: boolean;
    source?: string;
    coder_model?: string;
    reviewer_model?: string;
    report_model?: string;
  };
  assets?: Array<{
    title: string;
    profile?: {
      rows?: number;
      columns?: number;
      column_names?: string[];
      schema_fingerprint?: string;
      candidate_targets?: string[];
      candidate_features?: string[];
      quality_warnings?: string[];
      preview_rows?: Array<Record<string, unknown>>;
    };
  }>;
  messages?: AgentMessage[];
  cells?: Array<{
    id: string;
    status?: string;
    execution_mode?: string;
    coder_source?: string;
  }>;
  profile_snapshots?: Array<{
    id: string;
    created_at?: string;
    profile?: {
      rows?: number;
      columns?: number;
      schema_fingerprint?: string;
    };
  }>;
  safety_events?: Array<{
    at?: string;
    message?: string;
    code_preview?: string;
  }>;
  math?: {
    mode?: string;
    override_margin?: number;
    v2_state_summary?: {
      successful_cell_count?: number;
      safety_event_count?: number;
      recent_failure_classes?: string[];
      run_status?: string;
    };
  };
};

type LlmConfig = {
  workspace: {
    configured: boolean;
    enabled: boolean;
    base_url: string;
    api_key_configured: boolean;
    coder_model: string;
    reviewer_model: string;
    report_model: string;
    label: string;
  };
  environment: {
    enabled: boolean;
    ready: boolean;
    base_url_configured: boolean;
    api_key_configured: boolean;
    coder_model: string;
    reviewer_model: string;
    report_model: string;
  };
  resolved: {
    enabled: boolean;
    ready: boolean;
    source: string;
    coder_model: string;
    reviewer_model: string;
    report_model: string;
  };
};

type HistoryItem = {
  id: string;
  run_id?: string;
  title: string;
  status: string;
  summary?: string;
};

type LlmFormState = {
  enabled: boolean;
  base_url: string;
  api_key: string;
  clear_api_key: boolean;
  coder_model: string;
  reviewer_model: string;
  report_model: string;
  label: string;
};

type SendMessageInput = {
  message: string;
  userCode: string;
  interventionNote: string;
  executionMode: string;
};

type ReportResponse = {
  session: AgentSession;
  report: {
    path: string;
    markdown: string;
  };
};

type NotebookResponse = {
  session: AgentSession;
  notebook: {
    path: string;
    download_path: string;
  };
};

const EMPTY_LLM_FORM: LlmFormState = {
  enabled: false,
  base_url: "",
  api_key: "",
  clear_api_key: false,
  coder_model: "",
  reviewer_model: "",
  report_model: "",
  label: "",
};

function workspaceFormState(workspace?: LlmConfig["workspace"]): LlmFormState {
  if (!workspace) {
    return { ...EMPTY_LLM_FORM };
  }
  return {
    enabled: workspace.enabled,
    base_url: workspace.base_url,
    api_key: "",
    clear_api_key: false,
    coder_model: workspace.coder_model,
    reviewer_model: workspace.reviewer_model,
    report_model: workspace.report_model,
    label: workspace.label,
  };
}

function humanInterventionRequired(message?: AgentMessage): boolean {
  return Boolean(message?.human_intervention?.required);
}

function formatFallbackReason(reason?: string): string {
  return reason || "override_applied";
}

function formatMaybeNumber(value?: number): string {
  return typeof value === "number" ? value.toFixed(3) : "-";
}

function artifactLabelFromPath(path?: string): string {
  if (!path) {
    return "";
  }
  const normalized = path.replace(/\\/g, "/").split("?")[0].split("#")[0];
  return normalized.split("/").filter(Boolean).pop() || "notebook.ipynb";
}

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
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const datasetSelectRef = useRef<HTMLSelectElement | null>(null);
  const messageInputRef = useRef<HTMLTextAreaElement | null>(null);
  const manualCodeInputRef = useRef<HTMLTextAreaElement | null>(null);
  const interventionNoteInputRef = useRef<HTMLInputElement | null>(null);
  const executionModeSelectRef = useRef<HTMLSelectElement | null>(null);

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
  const firstProfile = currentSession?.assets?.[0]?.profile;
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
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Trusted execution control</p>
            <h3>Data Lab Agent</h3>
            <p>Natural language data analysis with LLM planning, trusted local Python execution, repair traces, human intervention, and exportable evidence.</p>
          </div>
        </div>
        <div className="list-card static-card risk-notice" role="note" aria-label="Trusted mode risk notice">
          <strong>Trusted mode notice</strong>
          <p className="muted">
            Python execution can read files and use network access available to the server process. Keep trusted execution disabled unless the deployment, datasets, and users are approved for local code execution.
          </p>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Session Title</span>
            <input ref={titleInputRef} value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            <span>Dataset</span>
            <select ref={datasetSelectRef} value={assetId} onChange={(event) => setAssetId(event.target.value)}>
              <option value="">Select dataset</option>
              {datasetAssets.map((asset) => (
                <option key={asset.id} value={asset.id}>{asset.title}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="action-row">
          <button
            className="primary-button"
            type="button"
            disabled={!workspaceId || !assetId || createSessionMutation.isPending}
            onClick={() => {
              const nextTitle = titleInputRef.current?.value ?? title;
              const nextAssetId = datasetSelectRef.current?.value ?? assetId;
              setTitle(nextTitle);
              setAssetId(nextAssetId);
              createSessionMutation.mutate({ nextTitle, nextAssetId });
            }}
          >
            Create Session
          </button>
          <span className="muted">Feature flag required: DATA_LAB_AGENT_ENABLED=true.</span>
          {permalinkHref ? (
            <a className="ghost-button" href={permalinkHref}>Open Session Link</a>
          ) : null}
        </div>
        {assetsQuery.isError ? (
          <InlineErrorState title="Datasets could not load" description={(assetsQuery.error as Error).message} />
        ) : null}
        {!assetsQuery.isError && assetsQuery.isSuccess && !datasetAssets.length ? (
          <InlineEmptyState title="No datasets available" description="Upload or register a dataset asset before creating a Data Lab Agent session." />
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Scoped LLM</p>
            <h3>Agent Model Config</h3>
            <p>
              Resolved: {llmConfigQuery.data?.resolved.ready ? "ready" : "fallback"} via {llmConfigQuery.data?.resolved.source || "none"}.
            </p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Enable scoped LLM</span>
            <select
              value={llmForm.enabled ? "true" : "false"}
              onChange={(event) => setLlmForm((current) => ({ ...current, enabled: event.target.value === "true" }))}
            >
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
          </label>
          <label className="field">
            <span>Base URL</span>
            <input value={llmForm.base_url} onChange={(event) => setLlmForm((current) => ({ ...current, base_url: event.target.value }))} placeholder="https://gateway.example/v1" />
          </label>
          <label className="field">
            <span>API Key</span>
            <input value={llmForm.api_key} onChange={(event) => setLlmForm((current) => ({ ...current, api_key: event.target.value }))} placeholder={llmConfigQuery.data?.workspace.api_key_configured ? "Stored; leave blank to keep" : "Optional for local gateways"} />
          </label>
          <label className="field">
            <span>Stored Key</span>
            <select
              value={llmForm.clear_api_key ? "clear" : "keep"}
              onChange={(event) => setLlmForm((current) => ({ ...current, clear_api_key: event.target.value === "clear" }))}
            >
              <option value="keep">Keep stored key</option>
              <option value="clear">Clear stored key</option>
            </select>
          </label>
          <label className="field">
            <span>Label</span>
            <input value={llmForm.label} onChange={(event) => setLlmForm((current) => ({ ...current, label: event.target.value }))} placeholder="Workspace-scoped agent config" />
          </label>
          <label className="field">
            <span>Coder Model</span>
            <input value={llmForm.coder_model} onChange={(event) => setLlmForm((current) => ({ ...current, coder_model: event.target.value }))} />
          </label>
          <label className="field">
            <span>Reviewer Model</span>
            <input value={llmForm.reviewer_model} onChange={(event) => setLlmForm((current) => ({ ...current, reviewer_model: event.target.value }))} />
          </label>
          <label className="field">
            <span>Report Model</span>
            <input value={llmForm.report_model} onChange={(event) => setLlmForm((current) => ({ ...current, report_model: event.target.value }))} />
          </label>
        </div>
        <div className="action-row">
          <button className="ghost-button" type="button" onClick={loadWorkspaceConfig}>Load Stored</button>
          <button className="primary-button" type="button" disabled={!workspaceId || saveLlmConfigMutation.isPending} onClick={() => saveLlmConfigMutation.mutate()}>
            Save LLM Config
          </button>
          <button className="ghost-button" type="button" disabled={!workspaceId || testLlmConfigMutation.isPending} onClick={() => testLlmConfigMutation.mutate()}>
            Test
          </button>
        </div>
        {llmTestResult ? <p className="muted">{llmTestResult}</p> : null}
        {llmConfigQuery.isError ? (
          <InlineErrorState title="LLM config could not load" description={(llmConfigQuery.error as Error).message} />
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">History</p>
            <h3>Agent Sessions</h3>
          </div>
        </div>
        <div className="list-stack">
          {historyQuery.isError ? (
            <InlineErrorState title="Agent sessions could not load" description={(historyQuery.error as Error).message} />
          ) : null}
          {!historyQuery.isError && historyQuery.isSuccess && !historyQuery.data?.agent_sessions?.length ? (
            <InlineEmptyState title="No agent sessions yet" description="Create a session to begin the analysis loop." />
          ) : null}
          {(historyQuery.data?.agent_sessions || []).map((item) => {
            const runId = item.run_id || item.id;
            return (
              <button
                key={item.id}
                className={selectedRunId === runId ? "list-card selected" : "list-card"}
                type="button"
                onClick={() => setSelectedRunId(runId)}
              >
                <div className="list-card-title">
                  <strong>{item.title}</strong>
                  <span>{item.status}</span>
                </div>
                <p>{item.summary || "Open the session to inspect messages and cells."}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="panel panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Conversation</p>
            <h3>{currentSession?.title || "No session selected"}</h3>
            {firstProfile ? (
              <p>
                {firstProfile.rows || 0} rows, {firstProfile.columns || 0} columns.
                {firstProfile.schema_fingerprint ? ` Fingerprint: ${firstProfile.schema_fingerprint}.` : ""}
              </p>
            ) : null}
            {currentSession ? (
              <p className="muted">
                Mode: {currentSession.executor?.active_mode || "not run"}.
                LLM: {currentSession.llm?.ready ? `${currentSession.llm.source} ${currentSession.llm.coder_model}` : "rules fallback"}.
                ARBITER: {currentSession.math?.mode || "off"}.
                Margin: {typeof currentSession.math?.override_margin === "number" ? currentSession.math.override_margin.toFixed(2) : "-"}.
                Cells: {currentSession.cells?.length || 0}. Snapshots: {currentSession.profile_snapshots?.length || 0}. Safety events: {currentSession.safety_events?.length || 0}.
              </p>
            ) : null}
          </div>
          <div className="action-row">
            {selectedRunId ? (
              <button
                className="ghost-button"
                type="button"
                disabled={!currentSession || notebookMutation.isPending}
                aria-busy={notebookMutation.isPending}
                aria-describedby="data-lab-notebook-status"
                onClick={() => notebookMutation.mutate()}
              >
                {notebookMutation.isPending ? "Preparing Notebook" : "Prepare Notebook"}
              </button>
            ) : null}
            {notebookHref ? (
              <a className="ghost-button" href={notebookHref} download>Download Notebook</a>
            ) : null}
            {permalinkHref ? (
              <a className="ghost-button" href={permalinkHref}>
                Permalink
              </a>
            ) : null}
          </div>
        </div>
        <div id="data-lab-notebook-status" className="list-card static-card notebook-status-card" role="status" aria-live="polite">
          <div className="list-card-title">
            <strong>Notebook Export</strong>
            <span className={notebookHref ? "state-pill success" : notebookMutation.isPending ? "state-pill pending" : "state-pill"}>
              {notebookExportState}
            </span>
          </div>
          <p>{notebookExportMessage}</p>
          <div className="inline-metrics">
            <span>Run: {selectedRunId ? selectedRunId.slice(0, 8) : "none"}</span>
            <span>Source: {notebookExportSource}</span>
          </div>
          {notebookArtifactLabel ? (
            <p className="muted">Artifact: {notebookArtifactLabel}</p>
          ) : null}
        </div>
        {sessionQuery.isError ? (
          <InlineErrorState title="Agent session could not load" description={(sessionQuery.error as Error).message} />
        ) : currentSession ? (
          <div className="detail-grid">
            <div className="detail-column">
              {needsHuman ? (
                <div className="list-card static-card">
                  <strong>Human intervention required</strong>
                  <p>{latestAssistantWithCode?.human_intervention?.reason || "Automated repair could not complete this cell."}</p>
                  {latestAssistantWithCode?.human_intervention?.next_action ? (
                    <p className="muted">{latestAssistantWithCode.human_intervention.next_action}</p>
                  ) : null}
                  <div className="action-row">
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => {
                        setManualCode(latestAssistantWithCode?.code || "");
                        setInterventionNote("Manual correction after automated repair failed.");
                      }}
                    >
                      Edit Failed Code
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      disabled={!latestPrompt || sendMessageMutation.isPending}
                      onClick={retryLatestPrompt}
                    >
                      Retry Last Prompt
                    </button>
                  </div>
                </div>
              ) : null}

              <label className="field">
                <span>Instruction</span>
                <textarea ref={messageInputRef} value={message} onChange={(event) => setMessage(event.target.value)} rows={4} />
              </label>
              <label className="field">
                <span>Execution Mode</span>
                <select ref={executionModeSelectRef} value={executionMode} onChange={(event) => setExecutionMode(event.target.value)}>
                  <option value="">Session default</option>
                  <option value="subprocess_replay">Trusted subprocess replay</option>
                  <option value="auto">Auto dual mode</option>
                  <option value="ipython_kernel">IPython kernel</option>
                </select>
              </label>
              <label className="field">
                <span>Manual code override</span>
                <textarea ref={manualCodeInputRef} value={manualCode} onChange={(event) => setManualCode(event.target.value)} rows={8} placeholder="Optional Python code for human intervention." />
              </label>
              <label className="field">
                <span>Human note</span>
                <input ref={interventionNoteInputRef} value={interventionNote} onChange={(event) => setInterventionNote(event.target.value)} placeholder="Why this manual code is being used." />
              </label>
              <div className="action-row">
                <button
                  className="primary-button"
                  type="button"
                  disabled={!selectedRunId || (!message.trim() && !manualCode.trim()) || sendMessageMutation.isPending}
                  onClick={runMessage}
                >
                  {manualCode.trim() ? "Run Manual Code" : "Run Message"}
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  disabled={!selectedRunId || sendMessageMutation.isPending || (!message.trim() && !manualCode.trim())}
                  onClick={() => {
                    setManualCode("");
                    setInterventionNote("");
                  }}
                >
                  Clear Draft
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  disabled={!selectedRunId || reportMutation.isPending}
                  onClick={() => reportMutation.mutate()}
                >
                  Generate Report
                </button>
              </div>

              <div className="list-card static-card">
                <strong>Dataset Context</strong>
                <p className="muted">
                  Suggested targets: {(firstProfile?.candidate_targets || []).join(", ") || "none"}.
                </p>
                {firstProfile?.quality_warnings?.length ? (
                  <ul>
                    {firstProfile.quality_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No major quality warnings detected in the initial profile.</p>
                )}
                <details>
                  <summary>Profile Preview</summary>
                  <pre>{JSON.stringify(firstProfile || {}, null, 2)}</pre>
                </details>
              </div>

              {currentSession.safety_events?.length ? (
                <details className="list-card static-card">
                  <summary>Safety events</summary>
                  <pre>{JSON.stringify(currentSession.safety_events, null, 2)}</pre>
                </details>
              ) : null}
              {currentSession.math?.v2_state_summary ? (
                <div className="list-card static-card">
                  <strong>ARBITER v2 state</strong>
                  <p className="muted">
                    mode {currentSession.math?.mode || "off"} / override margin {typeof currentSession.math?.override_margin === "number" ? currentSession.math.override_margin.toFixed(2) : "-"} / successful cells {currentSession.math.v2_state_summary.successful_cell_count || 0} / safety events {currentSession.math.v2_state_summary.safety_event_count || 0} / run {currentSession.math.v2_state_summary.run_status || "unknown"}
                  </p>
                  <p className="muted">
                    Recent failures: {(currentSession.math.v2_state_summary.recent_failure_classes || []).join(", ") || "none"}.
                  </p>
                  <details>
                    <summary>Raw ARBITER state</summary>
                    <pre>{JSON.stringify(currentSession.math.v2_state_summary, null, 2)}</pre>
                  </details>
                </div>
              ) : null}

              {reportMarkdown ? (
                <div className="list-card static-card">
                  <strong>Generated Report</strong>
                  <pre>{reportMarkdown}</pre>
                </div>
              ) : null}
            </div>

            <div className="detail-column">
              <h4>Messages</h4>
              <div className="list-stack">
                {messages.map((item) => (
                  <article key={item.id} className="list-card static-card">
                    <div className="list-card-title">
                      <strong>{item.role}</strong>
                      <span>{item.status || ""}</span>
                    </div>
                    <p>{item.content}</p>
                    {item.coder_source ? <p className="muted">Coder: {item.coder_source}. Mode: {item.execution_mode || "not executed"}.</p> : null}
                    {item.human_intervention?.required ? (
                      <p className="muted">
                        Human intervention required. {item.human_intervention.reason || ""}
                      </p>
                    ) : null}
                    {item.human_intervention?.provided ? (
                      <p className="muted">
                        Manual note: {item.human_intervention.note || "Provided manually."}
                      </p>
                    ) : null}
                    {item.code ? <pre>{item.code}</pre> : null}
                    {item.execution?.stdout ? <pre>{item.execution.stdout}</pre> : null}
                    {item.execution?.stderr ? <pre>{item.execution.stderr}</pre> : null}
                    {item.execution?.error ? <pre>{item.execution.error}</pre> : null}
                    {item.risk_notes?.length ? (
                      <p className="muted">Risk notes: {item.risk_notes.join(" | ")}</p>
                    ) : null}
                    {item.profile_snapshot ? (
                      <p className="muted">
                        Snapshot: {item.profile_snapshot.rows || 0} rows, {item.profile_snapshot.columns || 0} columns, {item.profile_snapshot.schema_fingerprint || "no fingerprint"}.
                      </p>
                    ) : null}
                    {item.artifact_manifest?.count ? (
                      <div>
                        <p className="muted">Artifacts: {item.artifact_manifest.count} files, {item.artifact_manifest.image_count || 0} images.</p>
                        {item.execution?.artifacts?.length ? (
                          <ul>
                            {item.execution.artifacts.map((artifact) => (
                              <li key={`${item.id}-${artifact.path}`}>{artifact.relative_path || artifact.name}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : null}
                    {item.repair_trace?.length ? (
                      <details>
                        <summary>Repair trace</summary>
                        <pre>{JSON.stringify(item.repair_trace, null, 2)}</pre>
                      </details>
                    ) : null}
                    {item.math_trace ? (
                      <div className="list-card static-card">
                        <strong>ARBITER trace</strong>
                        <p className="muted">
                          mode {item.math_trace.mode || "off"} / override margin {typeof item.math_trace.override_margin === "number" ? item.math_trace.override_margin.toFixed(2) : "-"} / run {item.math_trace.v2_state_summary?.run_status || "unknown"}
                        </p>
                        {item.math_trace.retrieval?.v2?.comparison ? (
                          <p className="muted">
                            retrieval baseline {item.math_trace.retrieval.v2.comparison.baseline_choice || "none"} / proposed {item.math_trace.retrieval.v2.comparison.proposed_choice || "none"} / chosen {item.math_trace.retrieval.v2.comparison.chosen_choice || "none"} / fallback {formatFallbackReason(item.math_trace.retrieval.v2.comparison.fallback_reason)} / advantage {formatMaybeNumber(item.math_trace.retrieval.v2.comparison.advantage)}
                          </p>
                        ) : null}
                        {item.math_trace.repair_decisions?.length ? (
                          <div className="list-stack">
                            {item.math_trace.repair_decisions.map((decision, index) => (
                              <p key={`${item.id}-repair-${index}`} className="muted">
                                repair {index + 1}: {decision.best_action || "unknown"} / {decision.error_class || "unknown"} / fallback {formatFallbackReason(decision.v2?.comparison?.fallback_reason)} / chosen {decision.v2?.comparison?.chosen_choice || decision.best_action || "unknown"}
                              </p>
                            ))}
                          </div>
                        ) : null}
                        <details>
                          <summary>Raw ARBITER trace</summary>
                          <pre>{JSON.stringify(item.math_trace, null, 2)}</pre>
                        </details>
                      </div>
                    ) : null}
                    {item.knowledge_cards?.length ? (
                      <details>
                        <summary>Knowledge cards</summary>
                        <div className="list-stack">
                          {item.knowledge_cards.map((card) => (
                            <div key={`${item.id}-${card.id}`} className="list-card static-card">
                              <div className="list-card-title">
                                <strong>{card.title}</strong>
                                <span>{card.source_type}</span>
                              </div>
                              <p>{card.summary}</p>
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}
                    {item.llm_trace_summary?.length ? (
                      <details>
                        <summary>LLM trace summary</summary>
                        <pre>{JSON.stringify(item.llm_trace_summary, null, 2)}</pre>
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <InlineEmptyState title="No session selected" description="Create or select a session to start the Data Lab Agent loop." />
        )}
        {mutationError ? (
          <InlineErrorState title="Request failed" description={(mutationError as Error).message} />
        ) : null}
      </section>
    </div>
  );
}
