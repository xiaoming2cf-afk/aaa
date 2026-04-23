import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api";

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
};

type AgentSession = {
  run_id: string;
  title: string;
  summary?: string;
  run_status?: string;
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
      quality_warnings?: string[];
    };
  }>;
  messages?: Array<{
    id: string;
    role: string;
    content: string;
    status?: string;
    code?: string;
    execution_mode?: string;
    coder_source?: string;
    knowledge_cards?: KnowledgeCard[];
    llm_trace_summary?: Array<{ role: string; source: string; summary?: string; fallback?: boolean; llm_error?: string }>;
    human_intervention?: { required?: boolean; provided?: boolean; note?: string; reason?: string; next_action?: string };
    artifact_manifest?: { count?: number; image_count?: number; total_size_bytes?: number; names?: string[] };
    profile_snapshot?: { rows?: number; columns?: number; schema_fingerprint?: string };
    execution?: {
      stdout?: string;
      stderr?: string;
      error?: string;
      artifacts?: Array<{ name: string; path: string; relative_path?: string }>;
    };
    repair_trace?: Array<{
      attempt: number;
      status: string;
      error: string;
      suggestion?: string;
      reviewer_source?: string;
      repair_strategy?: string;
    }>;
  }>;
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

export function DataLabAgentPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("Data Lab Agent Session");
  const [assetId, setAssetId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [message, setMessage] = useState("Show a concise overview of this dataset.");
  const [manualCode, setManualCode] = useState("");
  const [interventionNote, setInterventionNote] = useState("");
  const [executionMode, setExecutionMode] = useState("");
  const [llmForm, setLlmForm] = useState({
    enabled: false,
    base_url: "",
    api_key: "",
    clear_api_key: false,
    coder_model: "",
    reviewer_model: "",
    report_model: "",
    label: "",
  });
  const [llmTestResult, setLlmTestResult] = useState("");

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

  const createSessionMutation = useMutation({
    mutationFn: () => apiFetch<{ session: AgentSession }>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions`, {
      method: "POST",
      body: JSON.stringify({
        title,
        language: "Chinese",
        asset_ids: [assetId],
      }),
    }),
    onSuccess: (payload) => {
      setSelectedRunId(payload.session.run_id);
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
    mutationFn: () => apiFetch<{ session: AgentSession }>(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        message,
        user_code: manualCode,
        intervention_note: interventionNote,
        execution_mode: executionMode,
      }),
    }),
    onSuccess: () => {
      setManualCode("");
      setInterventionNote("");
      void queryClient.invalidateQueries({ queryKey: ["data-lab-agent-session", workspaceId, selectedRunId] });
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const reportMutation = useMutation({
    mutationFn: () => apiFetch(`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/report`, {
      method: "POST",
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["data-lab-agent-session", workspaceId, selectedRunId] });
    },
  });

  const currentSession = sessionQuery.data?.session;
  const firstProfile = currentSession?.assets?.[0]?.profile;
  const latestAssistant = [...(currentSession?.messages || [])].reverse().find((item) => item.role === "assistant" && item.code);
  const needsHuman = currentSession?.run_status === "needs_human_intervention"
    || latestAssistant?.human_intervention?.required;
  const mutationError = createSessionMutation.error
    || sendMessageMutation.error
    || reportMutation.error
    || saveLlmConfigMutation.error
    || testLlmConfigMutation.error;

  const loadWorkspaceConfig = (): void => {
    const workspace = llmConfigQuery.data?.workspace;
    if (!workspace) {
      return;
    }
    setLlmForm({
      enabled: workspace.enabled,
      base_url: workspace.base_url,
      api_key: "",
      clear_api_key: false,
      coder_model: workspace.coder_model,
      reviewer_model: workspace.reviewer_model,
      report_model: workspace.report_model,
      label: workspace.label,
    });
  };

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Clean-room runtime</p>
            <h3>Data Lab Agent</h3>
            <p>Natural language data analysis with LLM planning, safe Python execution, repair traces, human intervention, and exportable evidence.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Session Title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            <span>Dataset</span>
            <select value={assetId} onChange={(event) => setAssetId(event.target.value)}>
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
            onClick={() => createSessionMutation.mutate()}
          >
            Create Session
          </button>
          <span className="muted">Feature flag required: DATA_LAB_AGENT_ENABLED=true.</span>
        </div>
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
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">History</p>
            <h3>Agent Sessions</h3>
          </div>
        </div>
        <div className="list-stack">
          {(historyQuery.data?.agent_sessions || []).map((item) => (
            <button
              key={item.id}
              className={selectedRunId === (item.run_id || item.id) ? "list-card selected" : "list-card"}
              type="button"
              onClick={() => setSelectedRunId(item.run_id || item.id)}
            >
              <div className="list-card-title">
                <strong>{item.title}</strong>
                <span>{item.status}</span>
              </div>
              <p>{item.summary || "Open the session to inspect messages and cells."}</p>
            </button>
          ))}
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
              </p>
            ) : null}
          </div>
          {selectedRunId ? (
            <a className="ghost-button" href={`/api/workspaces/${workspaceId}/data-lab/agent/sessions/${selectedRunId}/notebook`}>
              Notebook
            </a>
          ) : null}
        </div>
        {currentSession ? (
          <div className="detail-grid">
            <div className="detail-column">
              {needsHuman ? (
                <div className="list-card static-card">
                  <strong>Human intervention required</strong>
                  <p>{latestAssistant?.human_intervention?.reason || "Automated repair could not complete this cell."}</p>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      setManualCode(latestAssistant?.code || "");
                      setInterventionNote("Manual correction after automated repair failed.");
                    }}
                  >
                    Edit Failed Code
                  </button>
                </div>
              ) : null}
              <label className="field">
                <span>Instruction</span>
                <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={4} />
              </label>
              <label className="field">
                <span>Execution Mode</span>
                <select value={executionMode} onChange={(event) => setExecutionMode(event.target.value)}>
                  <option value="">Session default</option>
                  <option value="subprocess_replay">Safe replay subprocess</option>
                  <option value="auto">Auto dual mode</option>
                  <option value="ipython_kernel">IPython kernel</option>
                </select>
              </label>
              <label className="field">
                <span>Manual code override</span>
                <textarea value={manualCode} onChange={(event) => setManualCode(event.target.value)} rows={8} placeholder="Optional Python code for human intervention." />
              </label>
              <label className="field">
                <span>Human note</span>
                <input value={interventionNote} onChange={(event) => setInterventionNote(event.target.value)} placeholder="Why this manual code is being used." />
              </label>
              <div className="action-row">
                <button
                  className="primary-button"
                  type="button"
                  disabled={!selectedRunId || sendMessageMutation.isPending}
                  onClick={() => sendMessageMutation.mutate()}
                >
                  {manualCode.trim() ? "Run Manual Code" : "Run Message"}
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
              <h4>Dataset Context</h4>
              <pre>{JSON.stringify(currentSession.assets || [], null, 2)}</pre>
            </div>
            <div className="detail-column">
              <h4>Messages</h4>
              <div className="list-stack">
                {(currentSession.messages || []).map((item) => (
                  <article key={item.id} className="list-card static-card">
                    <div className="list-card-title">
                      <strong>{item.role}</strong>
                      <span>{item.status || ""}</span>
                    </div>
                    <p>{item.content}</p>
                    {item.coder_source ? <p className="muted">Coder: {item.coder_source}. Mode: {item.execution_mode || "not executed"}.</p> : null}
                    {item.code ? <pre>{item.code}</pre> : null}
                    {item.execution?.stdout ? <pre>{item.execution.stdout}</pre> : null}
                    {item.execution?.error ? <pre>{item.execution.error}</pre> : null}
                    {item.profile_snapshot ? (
                      <p className="muted">
                        Snapshot: {item.profile_snapshot.rows || 0} rows, {item.profile_snapshot.columns || 0} columns, {item.profile_snapshot.schema_fingerprint || "no fingerprint"}.
                      </p>
                    ) : null}
                    {item.artifact_manifest?.count ? (
                      <p className="muted">Artifacts: {item.artifact_manifest.count} files, {item.artifact_manifest.image_count || 0} images.</p>
                    ) : null}
                    {item.repair_trace?.length ? (
                      <details>
                        <summary>Repair trace</summary>
                        <pre>{JSON.stringify(item.repair_trace, null, 2)}</pre>
                      </details>
                    ) : null}
                    {item.knowledge_cards?.length ? (
                      <details>
                        <summary>Knowledge cards</summary>
                        <pre>{JSON.stringify(item.knowledge_cards, null, 2)}</pre>
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
          <p className="muted">Create or select a session to start the Data Lab Agent loop.</p>
        )}
        {mutationError ? (
          <div className="list-card static-card">
            <strong>Request failed</strong>
            <p>{(mutationError as Error).message}</p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
