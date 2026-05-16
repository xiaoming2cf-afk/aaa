import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  FileJson,
  FlaskConical,
  History,
  LineChart,
  PlaySquare,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Table2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";

import { apiFetch } from "../api";
import { InlineEmptyState, InlineErrorState, LoadingState } from "../components/StatusPrimitives";
import type { AssetSummary, LlmConfig } from "../components/data-lab/types";
import { ActionLink, Badge, Button, Card, DataTable, Field, MetricCard, MetricPill, PageHeader, Stepper, Surface } from "../components/ui";
import { useI18n } from "../i18n";
import { DataLabAgentPage } from "./DataLabAgentPage";

type UseAppState = () => {
  workspaceId: string;
};

type DataLabSection = "dataset" | "preparation" | "model" | "results" | "history" | "optimization" | "agent";

type HistoryItem = {
  id?: string;
  run_id?: string;
  title?: string;
  status?: string;
  summary?: string;
  detail_path?: string;
  created_at?: string;
  updated_at?: string;
  finished_at?: string;
};

type DataLabHistoryResponse = {
  processing?: HistoryItem[];
  models?: HistoryItem[];
  optimization?: HistoryItem[];
  agent_sessions?: HistoryItem[];
};

type CatalogFamily = {
  slug: string;
  title?: string;
  name?: string;
  summary?: string;
  methods?: Array<{
    slug: string;
    name?: string;
    title?: string;
    description?: string;
  }>;
};

type DataLabCatalogResponse = {
  processing_families?: CatalogFamily[];
  model_families?: CatalogFamily[];
};

type OptimizationCatalogResponse = {
  defaults?: {
    optimizers?: string[];
    functions?: string[];
  };
  summary?: {
    optimizer_count?: number;
    function_count?: number;
  };
  suite_requirements?: {
    min_algorithms?: number;
    min_functions?: number;
    min_runs?: number;
  };
};

type AssetProfile = {
  rows?: number;
  columns?: number;
  column_names?: string[];
  candidate_targets?: string[];
  candidate_features?: string[];
  quality_warnings?: string[];
  preview_rows?: Array<Record<string, unknown>>;
  schema_fingerprint?: string;
};

type ResultTarget = {
  type: "processing" | "models" | "optimization";
  id: string;
  title: string;
};

type ApiPayload = Record<string, unknown>;

const dataLabSections: Array<{
  id: DataLabSection;
  icon: JSX.Element;
  i18nKey: string;
}> = [
  { id: "dataset", icon: <Database aria-hidden="true" />, i18nKey: "dataLab.dataset" },
  { id: "preparation", icon: <Settings2 aria-hidden="true" />, i18nKey: "dataLab.preparation" },
  { id: "model", icon: <FlaskConical aria-hidden="true" />, i18nKey: "dataLab.model" },
  { id: "results", icon: <Table2 aria-hidden="true" />, i18nKey: "dataLab.results" },
  { id: "history", icon: <History aria-hidden="true" />, i18nKey: "dataLab.history" },
  { id: "optimization", icon: <PlaySquare aria-hidden="true" />, i18nKey: "dataLab.optimization" },
  { id: "agent", icon: <Bot aria-hidden="true" />, i18nKey: "dataLab.agent" },
];

function isDataLabSection(value: string | undefined): value is DataLabSection {
  return dataLabSections.some((section) => section.id === value);
}

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function timestampOf(item: HistoryItem): number {
  const raw = item.updated_at || item.finished_at || item.created_at || "";
  const timestamp = Date.parse(raw);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function listOf(value: unknown): HistoryItem[] {
  return Array.isArray(value) ? value.filter((item): item is HistoryItem => Boolean(item && typeof item === "object")) : [];
}

function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const normalized = (status || "").toLowerCase();
  if (["completed", "complete", "saved", "ready", "ok", "pass", "succeeded"].includes(normalized)) {
    return "success";
  }
  if (["blocked", "failed", "error", "needs_human_intervention"].includes(normalized)) {
    return "danger";
  }
  if (["running", "pending", "queued", "in_progress"].includes(normalized)) {
    return "info";
  }
  if (["warning", "warn"].includes(normalized)) {
    return "warning";
  }
  return "neutral";
}

function shortId(value?: string): string {
  return (value || "").slice(0, 8) || "pending";
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function profileFromPayload(payload: unknown): AssetProfile | undefined {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }
  const value = payload as Record<string, unknown>;
  if (value.profile && typeof value.profile === "object") {
    return value.profile as AssetProfile;
  }
  if (value.asset && typeof value.asset === "object" && (value.asset as Record<string, unknown>).profile) {
    return (value.asset as Record<string, unknown>).profile as AssetProfile;
  }
  return value as AssetProfile;
}

function resultTargetFromItem(bucket: ResultTarget["type"], item: HistoryItem): ResultTarget | null {
  const id = item.run_id || item.id || "";
  if (!id) {
    return null;
  }
  return {
    type: bucket,
    id,
    title: item.title || `${bucket} ${shortId(id)}`,
  };
}

export function DataLabHubPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();
  const { section } = useParams();
  const [searchParams] = useSearchParams();
  const activeSection: DataLabSection = isDataLabSection(section) ? section : "dataset";
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [guidePrompt, setGuidePrompt] = useState("Choose dependent, treatment, post, and controls for a causal model.");
  const [preparationForm, setPreparationForm] = useState({
    workflowGroup: "sample_preparation",
    includeColumns: "",
    requiredColumns: "",
    numericColumns: "",
    dateColumns: "",
    imputeMethod: "none",
  });
  const [modelForm, setModelForm] = useState({
    modelFamily: "",
    modelType: "ols",
    dependent: "",
    independents: "",
    controls: "",
    seriesColumns: "",
    entityColumn: "",
    timeColumn: "",
    treatmentColumn: "",
    postColumn: "",
  });
  const [plotForm, setPlotForm] = useState({
    chartType: "line",
    xColumn: "",
    yColumns: "",
    groupColumn: "",
    title: "Data Lab chart",
  });
  const [optimizationForm, setOptimizationForm] = useState({
    suiteLabel: "Optimization Suite",
    optimizerNames: "",
    functionNames: "",
    dimension: "30",
    epoch: "10",
    popSize: "20",
    runs: "3",
    workers: "3",
  });
  const initialResultTarget = useMemo<ResultTarget | null>(() => {
    const type = searchParams.get("type");
    const id = searchParams.get("id");
    if ((type === "processing" || type === "models" || type === "optimization") && id) {
      return { type, id, title: `${type} ${shortId(id)}` };
    }
    return null;
  }, [searchParams]);
  const [resultTarget, setResultTarget] = useState<ResultTarget | null>(initialResultTarget);

  const assetsQuery = useQuery({
    queryKey: ["assets", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: AssetSummary[] }>(`/api/workspaces/${workspaceId}/assets`),
  });
  const historyQuery = useQuery({
    queryKey: ["data-lab-history", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<DataLabHistoryResponse>(`/api/workspaces/${workspaceId}/data-lab/history`),
  });
  const catalogQuery = useQuery({
    queryKey: ["data-lab-catalog"],
    queryFn: () => apiFetch<DataLabCatalogResponse>("/api/data-lab/catalog"),
  });
  const profileQuery = useQuery({
    queryKey: ["asset-profile", workspaceId, selectedAssetId],
    enabled: Boolean(workspaceId && selectedAssetId),
    queryFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/assets/${selectedAssetId}/profile`),
  });
  const optimizationCatalogQuery = useQuery({
    queryKey: ["optimization-catalog"],
    queryFn: () => apiFetch<OptimizationCatalogResponse>("/api/optimization/catalog"),
  });
  const optimizationResultsQuery = useQuery({
    queryKey: ["optimization-results", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<{ items: HistoryItem[] }>(`/api/workspaces/${workspaceId}/optimization/results`),
  });
  const llmConfigQuery = useQuery({
    queryKey: ["data-lab-agent-llm-config", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<LlmConfig>(`/api/workspaces/${workspaceId}/data-lab/agent/llm-config`),
  });
  const resultDetailQuery = useQuery({
    queryKey: ["data-lab-result-detail", resultTarget?.type, resultTarget?.id],
    enabled: Boolean(resultTarget),
    queryFn: () => apiFetch<ApiPayload>(`/api/${resultTarget?.type === "optimization" ? "optimization/results" : `data-lab/results/${resultTarget?.type}`}/${resultTarget?.id}`),
  });

  const datasetAssets = useMemo(
    () => (assetsQuery.data?.items || []).filter((asset) => asset.kind?.startsWith("dataset_")),
    [assetsQuery.data],
  );
  const processingFamilies = catalogQuery.data?.processing_families || [];
  const modelFamilies = catalogQuery.data?.model_families || [];
  const selectedModelFamily = modelFamilies.find((family) => family.slug === modelForm.modelFamily) || modelFamilies[0];
  const selectedModelMethods = selectedModelFamily?.methods || [];
  const profile = profileFromPayload(profileQuery.data);
  const previewRows = profile?.preview_rows || [];
  const previewColumns = profile?.column_names?.slice(0, 8) || Object.keys(previewRows[0] || {}).slice(0, 8);
  const processing = listOf(historyQuery.data?.processing);
  const models = listOf(historyQuery.data?.models);
  const optimization = listOf(historyQuery.data?.optimization);
  const agentSessions = listOf(historyQuery.data?.agent_sessions);
  const recentItems = useMemo(
    () => [
      ...processing.map((item) => ({ ...item, bucket: "processing" as const })),
      ...models.map((item) => ({ ...item, bucket: "models" as const })),
      ...optimization.map((item) => ({ ...item, bucket: "optimization" as const })),
      ...agentSessions.map((item) => ({ ...item, bucket: "agent" as const })),
    ].sort((left, right) => timestampOf(right) - timestampOf(left)).slice(0, 8),
    [agentSessions, models, optimization, processing],
  );

  useEffect(() => {
    if (!selectedAssetId && datasetAssets.length) {
      setSelectedAssetId(datasetAssets[0].id);
    }
  }, [datasetAssets, selectedAssetId]);

  useEffect(() => {
    if (!preparationForm.workflowGroup && processingFamilies.length) {
      setPreparationForm((current) => ({ ...current, workflowGroup: processingFamilies[0].slug }));
    }
  }, [preparationForm.workflowGroup, processingFamilies]);

  useEffect(() => {
    if (!modelForm.modelFamily && selectedModelFamily) {
      setModelForm((current) => ({
        ...current,
        modelFamily: selectedModelFamily.slug,
        modelType: selectedModelFamily.methods?.[0]?.slug || current.modelType,
      }));
    }
  }, [modelForm.modelFamily, selectedModelFamily]);

  useEffect(() => {
    const defaults = optimizationCatalogQuery.data?.defaults;
    if (!defaults) {
      return;
    }
    setOptimizationForm((current) => ({
      ...current,
      optimizerNames: current.optimizerNames || (defaults.optimizers || []).slice(0, 3).join(", "),
      functionNames: current.functionNames || (defaults.functions || []).slice(0, 3).join(", "),
    }));
  }, [optimizationCatalogQuery.data]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!uploadFile) {
        throw new Error("Select a dataset file first.");
      }
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("description", uploadFile.name);
      formData.append("source_url", "");
      return apiFetch<{ asset: AssetSummary }>(`/api/workspaces/${workspaceId}/assets/upload`, {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: (payload) => {
      setSelectedAssetId(payload.asset.id);
      setUploadFile(null);
      void queryClient.invalidateQueries({ queryKey: ["assets", workspaceId] });
    },
  });

  const guideMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/variable-guide`, {
      method: "POST",
      body: JSON.stringify({ asset_id: selectedAssetId, prompt: guidePrompt }),
    }),
  });

  const preparationPayload = {
    asset_id: selectedAssetId,
    workflow_group: preparationForm.workflowGroup,
    include_columns: splitList(preparationForm.includeColumns),
    required_columns: splitList(preparationForm.requiredColumns),
    numeric_columns: splitList(preparationForm.numericColumns),
    date_columns: splitList(preparationForm.dateColumns),
    impute_method: preparationForm.imputeMethod,
  };
  const preparationPreviewMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/prepare/preview`, {
      method: "POST",
      body: JSON.stringify(preparationPayload),
    }),
  });
  const preparationMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/prepare`, {
      method: "POST",
      body: JSON.stringify(preparationPayload),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assets", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  const modelPayload = {
    asset_id: selectedAssetId,
    model_family: modelForm.modelFamily,
    model_type: modelForm.modelType,
    dependent: modelForm.dependent,
    independents: splitList(modelForm.independents),
    controls: splitList(modelForm.controls),
    series_columns: splitList(modelForm.seriesColumns),
    entity_column: modelForm.entityColumn,
    time_column: modelForm.timeColumn,
    treatment_column: modelForm.treatmentColumn,
    post_column: modelForm.postColumn,
  };
  const modelPreflightMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/models/preflight`, {
      method: "POST",
      body: JSON.stringify(modelPayload),
    }),
  });
  const modelMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/models`, {
      method: "POST",
      body: JSON.stringify(modelPayload),
    }),
    onSuccess: (payload) => {
      const recordId = String(payload.result_record_id || payload.record_id || (payload.result_record as Record<string, unknown> | undefined)?.id || "");
      if (recordId) {
        setResultTarget({ type: "models", id: recordId, title: String(payload.model_label || payload.model_type || recordId) });
      }
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });
  const plotMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/analysis/plot`, {
      method: "POST",
      body: JSON.stringify({
        asset_id: selectedAssetId,
        chart_type: plotForm.chartType,
        x_column: plotForm.xColumn,
        y_columns: splitList(plotForm.yColumns),
        group_column: plotForm.groupColumn,
        title: plotForm.title,
      }),
    }),
  });
  const optimizationMutation = useMutation({
    mutationFn: () => apiFetch<ApiPayload>(`/api/workspaces/${workspaceId}/optimization/run`, {
      method: "POST",
      body: JSON.stringify({
        suite_label: optimizationForm.suiteLabel,
        optimizer_names: splitList(optimizationForm.optimizerNames),
        function_names: splitList(optimizationForm.functionNames),
        dimension: Number(optimizationForm.dimension),
        epoch: Number(optimizationForm.epoch),
        pop_size: Number(optimizationForm.popSize),
        runs: Number(optimizationForm.runs),
        workers: Number(optimizationForm.workers),
      }),
    }),
    onSuccess: (payload) => {
      const result = (payload.result || payload.record || {}) as Record<string, unknown>;
      const id = String(result.result_record_id || result.id || "");
      if (id) {
        setResultTarget({ type: "optimization", id, title: String(result.suite_label || optimizationForm.suiteLabel) });
      }
      void queryClient.invalidateQueries({ queryKey: ["optimization-results", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["data-lab-history", workspaceId] });
    },
  });

  if (!isDataLabSection(section) && section !== undefined) {
    return <Navigate to="/data-lab/dataset" replace />;
  }

  if (!workspaceId) {
    return (
      <div className="data-lab-workspace-page">
        <InlineEmptyState title={t("dataLab.noWorkspace")} description={t("dataLab.noWorkspaceDescription")} />
      </div>
    );
  }

  const canUseDataset = Boolean(workspaceId && selectedAssetId);
  const riskSummary = llmConfigQuery.data?.risk_summary;
  const trustedEnabled = Boolean(riskSummary?.trusted_execution_enabled);

  return (
    <div className="data-lab-workspace-page" aria-label="Data Lab workspace">
      <Surface
        className="data-lab-workspace-hero"
        title={<PageHeader title={t("dataLab.title")} description={t("dataLab.description")} />}
        actions={<Badge tone={trustedEnabled ? "warning" : "success"}>{trustedEnabled ? `${t("dataLab.trustedExecution")} ${t("dataLab.enabled")}` : t("dataLab.trustedDisabled")}</Badge>}
      >
        <Stepper
          items={dataLabSections.map((item) => ({
            label: t(item.i18nKey),
            status: item.id === activeSection ? "active" : dataLabSections.findIndex((candidate) => candidate.id === item.id) < dataLabSections.findIndex((candidate) => candidate.id === activeSection) ? "complete" : "pending",
          }))}
        />
        <nav className="data-lab-tab-nav" aria-label="Data Lab sections">
          {dataLabSections.map((item) => (
            <Link className={item.id === activeSection ? "data-lab-tab-link is-active" : "data-lab-tab-link"} key={item.id} to={`/data-lab/${item.id}`}>
              {item.icon}
              <span>{t(item.i18nKey)}</span>
            </Link>
          ))}
        </nav>
      </Surface>

      <div className="data-lab-workspace-grid">
        <main className="data-lab-workspace-main">
          {activeSection === "dataset" ? (
            <DatasetSection
              canUseDataset={canUseDataset}
              datasetAssets={datasetAssets}
              guideMutation={guideMutation}
              guidePrompt={guidePrompt}
              onFileChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              profile={profile}
              profileError={profileQuery.error}
              profileLoading={profileQuery.isLoading}
              previewColumns={previewColumns}
              previewRows={previewRows}
              selectedAssetId={selectedAssetId}
              setGuidePrompt={setGuidePrompt}
              setSelectedAssetId={setSelectedAssetId}
              t={t}
              uploadFile={uploadFile}
              uploadMutation={uploadMutation}
            />
          ) : null}
          {activeSection === "preparation" ? (
            <PreparationSection
              canUseDataset={canUseDataset}
              form={preparationForm}
              previewMutation={preparationPreviewMutation}
              processingFamilies={processingFamilies}
              runMutation={preparationMutation}
              setForm={setPreparationForm}
              t={t}
            />
          ) : null}
          {activeSection === "model" ? (
            <ModelSection
              canUseDataset={canUseDataset}
              form={modelForm}
              modelFamilies={modelFamilies}
              modelMutation={modelMutation}
              plotForm={plotForm}
              plotMutation={plotMutation}
              preflightMutation={modelPreflightMutation}
              selectedMethods={selectedModelMethods}
              setForm={setModelForm}
              setPlotForm={setPlotForm}
              t={t}
            />
          ) : null}
          {activeSection === "results" ? (
            <ResultsSection
              historyItems={recentItems}
              resultDetailQuery={resultDetailQuery}
              resultTarget={resultTarget}
              setResultTarget={setResultTarget}
              t={t}
            />
          ) : null}
          {activeSection === "history" ? (
            <HistorySection
              agentSessions={agentSessions}
              historyQuery={historyQuery}
              models={models}
              optimization={optimization}
              processing={processing}
              setResultTarget={setResultTarget}
              t={t}
            />
          ) : null}
          {activeSection === "optimization" ? (
            <OptimizationSection
              catalog={optimizationCatalogQuery.data}
              catalogLoading={optimizationCatalogQuery.isLoading}
              form={optimizationForm}
              results={optimizationResultsQuery.data?.items || []}
              runMutation={optimizationMutation}
              setForm={setOptimizationForm}
              setResultTarget={setResultTarget}
              t={t}
            />
          ) : null}
          {activeSection === "agent" ? (
            <div className="data-lab-agent-embedded">
              <DataLabAgentPage useAppState={useAppState} />
            </div>
          ) : null}
        </main>

        <aside className="data-lab-workspace-inspector" aria-label="Data Lab inspector">
          <Surface title={t("dataLab.profile")} actions={<Database aria-hidden="true" />}>
            <div className="metric-strip">
              <MetricPill label={t("dataLab.rows")} value={profile?.rows ?? "-"} />
              <MetricPill label={t("dataLab.columns")} value={profile?.columns ?? "-"} />
              <MetricPill label="schema" value={shortId(profile?.schema_fingerprint)} />
            </div>
            {profile?.quality_warnings?.length ? (
              <ul className="data-lab-warning-list">
                {profile.quality_warnings.slice(0, 4).map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            ) : <p className="muted">{t("dataLab.noProfileWarnings")}</p>}
          </Surface>
          <Surface tone="warning" title={t("dataLab.preflightRequired")} actions={<ShieldCheck aria-hidden="true" />}>
            <p className="muted">{t("dataLab.notSandbox")}</p>
            <div className="metric-strip">
              <MetricPill label={t("dataLab.trustedExecution")} value={trustedEnabled ? t("dataLab.enabled") : t("dataLab.disabled")} tone={trustedEnabled ? "warning" : "success"} />
              <MetricPill label={t("dataLab.sandboxClaim")} value={riskSummary?.sandbox_claim || t("dataLab.none")} tone="warning" />
            </div>
          </Surface>
          <Surface title={t("dataLab.recentActivity")} actions={<Clock3 aria-hidden="true" />}>
            <div className="data-lab-inspector-list">
              {recentItems.length ? recentItems.slice(0, 5).map((item) => (
                <button
                  className="data-lab-inspector-item"
                  key={`${item.bucket}-${item.id || item.run_id}`}
                  type="button"
                  onClick={() => {
                    if (item.bucket !== "agent") {
                      const target = resultTargetFromItem(item.bucket, item);
                      if (target) {
                        setResultTarget(target);
                      }
                    }
                  }}
                >
                  <span>{item.bucket}</span>
                  <strong>{item.title || item.run_id || item.id}</strong>
                  <Badge tone={statusTone(item.status)}>{item.status || t("dataLab.unknown")}</Badge>
                </button>
              )) : <InlineEmptyState title={t("dataLab.noActivity")} description={t("dataLab.noActivityDescription")} />}
            </div>
          </Surface>
        </aside>
      </div>
    </div>
  );
}

function DatasetSection({
  canUseDataset,
  datasetAssets,
  guideMutation,
  guidePrompt,
  onFileChange,
  profile,
  profileError,
  profileLoading,
  previewColumns,
  previewRows,
  selectedAssetId,
  setGuidePrompt,
  setSelectedAssetId,
  t,
  uploadFile,
  uploadMutation,
}: {
  canUseDataset: boolean;
  datasetAssets: AssetSummary[];
  guideMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  guidePrompt: string;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  profile?: AssetProfile;
  profileError: unknown;
  profileLoading: boolean;
  previewColumns: string[];
  previewRows: Array<Record<string, unknown>>;
  selectedAssetId: string;
  setGuidePrompt: (value: string) => void;
  setSelectedAssetId: (value: string) => void;
  t: (key: string) => string;
  uploadFile: File | null;
  uploadMutation: UseMutationResult<{ asset: AssetSummary }, Error, void, unknown>;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface title={t("dataLab.upload")} actions={<Upload aria-hidden="true" />} tone="emphasis">
        <div className="form-grid">
          <Field label={t("dataLab.fileTypes")}>
            <input type="file" accept=".csv,.xlsx,.xls,.json" onChange={onFileChange} />
          </Field>
          <Field label={t("dataLab.selectDataset")}>
            <select value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value)}>
              <option value="">{t("dataLab.selectDatasetOption")}</option>
              {datasetAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.title}</option>)}
            </select>
          </Field>
        </div>
        <div className="action-row">
          <Button variant="primary" disabled={!uploadFile || uploadMutation.isPending} loading={uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>
            {t("dataLab.upload")}
          </Button>
          {uploadFile ? <span className="muted">{uploadFile.name}</span> : <span className="muted">{t("dataLab.fileGuidance")}</span>}
        </div>
        {uploadMutation.error ? <InlineErrorState title={t("dataLab.uploadFailed")} description={uploadMutation.error.message} /> : null}
      </Surface>

      <Surface title={t("dataLab.variableGuide")} actions={<LineChart aria-hidden="true" />}>
        <Field label={t("dataLab.prompt")}>
          <textarea value={guidePrompt} onChange={(event) => setGuidePrompt(event.target.value)} />
        </Field>
        <div className="action-row">
          <Button disabled={!canUseDataset || guideMutation.isPending} loading={guideMutation.isPending} onClick={() => guideMutation.mutate()} variant="primary">
            {t("dataLab.runGuide")}
          </Button>
        </div>
        <PayloadPreview payload={guideMutation.data} error={guideMutation.error} empty={t("dataLab.guideEmpty")} t={t} />
      </Surface>

      <Surface span title={t("dataLab.previewRows")} actions={<Table2 aria-hidden="true" />}>
        {profileLoading ? <LoadingState title={t("dataLab.loadingProfile")} description={t("dataLab.loadingProfileDescription")} /> : null}
        {profileError ? <InlineErrorState title={t("dataLab.profileUnavailable")} description={(profileError as Error).message} /> : null}
        {!profileLoading && !profileError && !previewRows.length ? <InlineEmptyState title={t("dataLab.noDatasetPreview")} description={t("dataLab.noDatasetPreviewDescription")} /> : null}
        {previewRows.length ? (
          <DataTable columns={previewColumns} rows={previewRows.slice(0, 8)} renderCell={(row, column) => stringifyValue(row[column])} />
        ) : null}
        {profile ? (
          <div className="metric-strip data-lab-profile-strip">
            <MetricCard label={t("dataLab.rows")} value={profile.rows ?? "-"} />
            <MetricCard label={t("dataLab.columns")} value={profile.columns ?? "-"} />
            <MetricCard label={t("dataLab.candidateTargets")} value={profile.candidate_targets?.slice(0, 3).join(", ") || "-"} />
          </div>
        ) : null}
      </Surface>
    </div>
  );
}

function PreparationSection({
  canUseDataset,
  form,
  previewMutation,
  processingFamilies,
  runMutation,
  setForm,
  t,
}: {
  canUseDataset: boolean;
  form: {
    workflowGroup: string;
    includeColumns: string;
    requiredColumns: string;
    numericColumns: string;
    dateColumns: string;
    imputeMethod: string;
  };
  previewMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  processingFamilies: CatalogFamily[];
  runMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  setForm: Dispatch<SetStateAction<typeof form>>;
  t: (key: string) => string;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface title={t("dataLab.preparation")} actions={<Settings2 aria-hidden="true" />} tone="emphasis">
        <div className="form-grid">
          <Field label={t("dataLab.workflow")}>
            <select value={form.workflowGroup} onChange={(event) => setForm((current) => ({ ...current, workflowGroup: event.target.value }))}>
              {processingFamilies.map((family) => <option key={family.slug} value={family.slug}>{family.title || family.slug}</option>)}
            </select>
          </Field>
          <Field label={t("dataLab.includeColumns")}>
            <input value={form.includeColumns} onChange={(event) => setForm((current) => ({ ...current, includeColumns: event.target.value }))} placeholder="y, x, date" />
          </Field>
          <Field label={t("dataLab.requiredColumns")}>
            <input value={form.requiredColumns} onChange={(event) => setForm((current) => ({ ...current, requiredColumns: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.numericColumns")}>
            <input value={form.numericColumns} onChange={(event) => setForm((current) => ({ ...current, numericColumns: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.dateColumns")}>
            <input value={form.dateColumns} onChange={(event) => setForm((current) => ({ ...current, dateColumns: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.imputeMethod")}>
            <select value={form.imputeMethod} onChange={(event) => setForm((current) => ({ ...current, imputeMethod: event.target.value }))}>
              <option value="none">none</option>
              <option value="mean">mean</option>
              <option value="median">median</option>
              <option value="zero">zero</option>
            </select>
          </Field>
        </div>
        <div className="action-row">
          <Button disabled={!canUseDataset || previewMutation.isPending} loading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
            {t("dataLab.previewPreparation")}
          </Button>
          <Button disabled={!canUseDataset || runMutation.isPending} loading={runMutation.isPending} onClick={() => runMutation.mutate()} variant="primary">
            {t("dataLab.savePrepared")}
          </Button>
        </div>
      </Surface>
      <Surface title={t("dataLab.preparationOutput")} actions={<FileJson aria-hidden="true" />}>
        <PayloadPreview payload={previewMutation.data || runMutation.data} error={previewMutation.error || runMutation.error} empty={t("dataLab.preparationEmpty")} t={t} />
      </Surface>
      <Surface span title={t("dataLab.catalog")}>
        <div className="data-lab-card-grid">
          {processingFamilies.map((family) => (
            <Card key={family.slug}>
              <h3>{family.title || family.slug}</h3>
              <p className="muted">{family.summary || t("dataLab.processingWorkflow")}</p>
              <Badge tone={family.slug === form.workflowGroup ? "success" : "neutral"}>{family.slug}</Badge>
            </Card>
          ))}
        </div>
      </Surface>
    </div>
  );
}

function ModelSection({
  canUseDataset,
  form,
  modelFamilies,
  modelMutation,
  plotForm,
  plotMutation,
  preflightMutation,
  selectedMethods,
  setForm,
  setPlotForm,
  t,
}: {
  canUseDataset: boolean;
  form: {
    modelFamily: string;
    modelType: string;
    dependent: string;
    independents: string;
    controls: string;
    seriesColumns: string;
    entityColumn: string;
    timeColumn: string;
    treatmentColumn: string;
    postColumn: string;
  };
  modelFamilies: CatalogFamily[];
  modelMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  plotForm: {
    chartType: string;
    xColumn: string;
    yColumns: string;
    groupColumn: string;
    title: string;
  };
  plotMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  preflightMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  selectedMethods: NonNullable<CatalogFamily["methods"]>;
  setForm: Dispatch<SetStateAction<typeof form>>;
  setPlotForm: Dispatch<SetStateAction<typeof plotForm>>;
  t: (key: string) => string;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface title={t("dataLab.model")} actions={<FlaskConical aria-hidden="true" />} tone="emphasis">
        <div className="form-grid">
          <Field label={t("dataLab.family")}>
            <select
              value={form.modelFamily}
              onChange={(event) => {
                const family = modelFamilies.find((item) => item.slug === event.target.value);
                setForm((current) => ({ ...current, modelFamily: event.target.value, modelType: family?.methods?.[0]?.slug || current.modelType }));
              }}
            >
              {modelFamilies.map((family) => <option key={family.slug} value={family.slug}>{family.title || family.slug}</option>)}
            </select>
          </Field>
          <Field label={t("dataLab.method")}>
            <select value={form.modelType} onChange={(event) => setForm((current) => ({ ...current, modelType: event.target.value }))}>
              {selectedMethods.map((method) => <option key={method.slug} value={method.slug}>{method.name || method.title || method.slug}</option>)}
              {!selectedMethods.length ? <option value={form.modelType}>{form.modelType}</option> : null}
            </select>
          </Field>
          <Field label={t("dataLab.dependent")}>
            <input value={form.dependent} onChange={(event) => setForm((current) => ({ ...current, dependent: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.independents")}>
            <input value={form.independents} onChange={(event) => setForm((current) => ({ ...current, independents: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.controls")}>
            <input value={form.controls} onChange={(event) => setForm((current) => ({ ...current, controls: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.seriesColumns")}>
            <input value={form.seriesColumns} onChange={(event) => setForm((current) => ({ ...current, seriesColumns: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.entityTime")}>
            <input value={form.entityColumn} onChange={(event) => setForm((current) => ({ ...current, entityColumn: event.target.value }))} placeholder="entity column" />
          </Field>
          <Field label={t("dataLab.timeColumn")}>
            <input value={form.timeColumn} onChange={(event) => setForm((current) => ({ ...current, timeColumn: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.treatmentPost")}>
            <input value={form.treatmentColumn} onChange={(event) => setForm((current) => ({ ...current, treatmentColumn: event.target.value }))} placeholder="treatment" />
          </Field>
          <Field label={t("dataLab.postColumn")}>
            <input value={form.postColumn} onChange={(event) => setForm((current) => ({ ...current, postColumn: event.target.value }))} />
          </Field>
        </div>
        <div className="action-row">
          <Button disabled={!canUseDataset || preflightMutation.isPending} loading={preflightMutation.isPending} onClick={() => preflightMutation.mutate()}>
            {t("dataLab.preflight")}
          </Button>
          <Button disabled={!canUseDataset || modelMutation.isPending} loading={modelMutation.isPending} onClick={() => modelMutation.mutate()} variant="primary">
            {t("dataLab.runModel")}
          </Button>
        </div>
      </Surface>
      <Surface title={t("dataLab.modelOutput")}>
        <PayloadPreview payload={modelMutation.data || preflightMutation.data} error={modelMutation.error || preflightMutation.error} empty={t("dataLab.modelOutputEmpty")} t={t} />
      </Surface>
      <Surface span title={t("dataLab.chart")}>
        <div className="form-grid">
          <Field label={t("dataLab.chartType")}>
            <select value={plotForm.chartType} onChange={(event) => setPlotForm((current) => ({ ...current, chartType: event.target.value }))}>
              <option value="line">line</option>
              <option value="scatter">scatter</option>
              <option value="bar">bar</option>
              <option value="histogram">histogram</option>
            </select>
          </Field>
          <Field label={t("dataLab.xColumn")}>
            <input value={plotForm.xColumn} onChange={(event) => setPlotForm((current) => ({ ...current, xColumn: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.yColumns")}>
            <input value={plotForm.yColumns} onChange={(event) => setPlotForm((current) => ({ ...current, yColumns: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.groupColumn")}>
            <input value={plotForm.groupColumn} onChange={(event) => setPlotForm((current) => ({ ...current, groupColumn: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.titleLabel")}>
            <input value={plotForm.title} onChange={(event) => setPlotForm((current) => ({ ...current, title: event.target.value }))} />
          </Field>
        </div>
        <div className="action-row">
          <Button disabled={!canUseDataset || plotMutation.isPending} loading={plotMutation.isPending} onClick={() => plotMutation.mutate()}>
            {t("dataLab.runPlot")}
          </Button>
        </div>
        <PayloadPreview payload={plotMutation.data} error={plotMutation.error} empty={t("dataLab.plotEmpty")} t={t} />
      </Surface>
    </div>
  );
}

function ResultsSection({
  historyItems,
  resultDetailQuery,
  resultTarget,
  setResultTarget,
  t,
}: {
  historyItems: Array<HistoryItem & { bucket: "processing" | "models" | "optimization" | "agent" }>;
  resultDetailQuery: UseQueryResult<ApiPayload, Error>;
  resultTarget: ResultTarget | null;
  setResultTarget: (target: ResultTarget | null) => void;
  t: (key: string) => string;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface title={t("dataLab.results")} actions={<Table2 aria-hidden="true" />}>
        <div className="data-lab-result-list">
          {historyItems.filter((item) => item.bucket !== "agent").map((item) => {
            const target = resultTargetFromItem(item.bucket, item);
            return (
              <button key={`${item.bucket}-${item.id || item.run_id}`} type="button" className="data-lab-result-row" onClick={() => target && setResultTarget(target)}>
                <span>{item.bucket}</span>
                <strong>{item.title || item.id || item.run_id}</strong>
                <Badge tone={statusTone(item.status)}>{item.status || t("dataLab.unknown")}</Badge>
              </button>
            );
          })}
        </div>
        {!historyItems.some((item) => item.bucket !== "agent") ? <InlineEmptyState title={t("dataLab.noResults")} description={t("dataLab.noResultsDescription")} /> : null}
      </Surface>
      <Surface title={resultTarget?.title || t("dataLab.resultDetail")} actions={<FileJson aria-hidden="true" />} tone="emphasis">
        {resultDetailQuery.isLoading ? <LoadingState title={t("dataLab.loadingResult")} description={t("dataLab.loadingResultDescription")} /> : null}
        <PayloadPreview payload={resultDetailQuery.data} error={resultDetailQuery.error} empty={t("dataLab.resultEmpty")} t={t} />
        {resultTarget ? (
          <ActionLink href={`/api/${resultTarget.type === "optimization" ? "optimization/results" : `data-lab/results/${resultTarget.type}`}/${resultTarget.id}`} variant="ghost">
            {t("dataLab.openResult")}
          </ActionLink>
        ) : null}
      </Surface>
      <Surface span title={t("dataLab.manifest")} actions={<CheckCircle2 aria-hidden="true" />}>
        <p className="muted">
          {t("dataLab.manifestText")}
        </p>
      </Surface>
    </div>
  );
}

function HistorySection({
  agentSessions,
  historyQuery,
  models,
  optimization,
  processing,
  setResultTarget,
  t,
}: {
  agentSessions: HistoryItem[];
  historyQuery: UseQueryResult<DataLabHistoryResponse, Error>;
  models: HistoryItem[];
  optimization: HistoryItem[];
  processing: HistoryItem[];
  setResultTarget: (target: ResultTarget | null) => void;
  t: (key: string) => string;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface span title={t("dataLab.history")} actions={<RefreshCw aria-hidden="true" />}>
        {historyQuery.isLoading ? <LoadingState title={t("dataLab.loadingHistory")} description={t("dataLab.loadingHistoryDescription")} /> : null}
        {historyQuery.error ? <InlineErrorState title={t("dataLab.historyUnavailable")} description={historyQuery.error.message} /> : null}
        <div className="data-lab-history-board">
          <HistoryBucket title={t("dataLab.processing")} type="processing" items={processing} setResultTarget={setResultTarget} t={t} />
          <HistoryBucket title={t("dataLab.models")} type="models" items={models} setResultTarget={setResultTarget} t={t} />
          <HistoryBucket title={t("dataLab.optimization")} type="optimization" items={optimization} setResultTarget={setResultTarget} t={t} />
          <HistoryBucket title={t("dataLab.agentSessions")} items={agentSessions} t={t} />
        </div>
      </Surface>
    </div>
  );
}

function HistoryBucket({
  items,
  setResultTarget,
  title,
  type,
  t,
}: {
  items: HistoryItem[];
  setResultTarget?: (target: ResultTarget | null) => void;
  title: string;
  type?: ResultTarget["type"];
  t: (key: string) => string;
}): JSX.Element {
  return (
    <section className="data-lab-history-bucket">
      <h3>{title}</h3>
      {items.length ? items.map((item) => (
        <button
          className="data-lab-history-item"
          key={item.id || item.run_id || item.title}
          type="button"
          onClick={() => {
            if (type && setResultTarget) {
              setResultTarget(resultTargetFromItem(type, item));
            }
          }}
        >
          <strong>{item.title || item.id || item.run_id}</strong>
          <Badge tone={statusTone(item.status)}>{item.status || t("dataLab.unknown")}</Badge>
          <span>{item.summary || t("dataLab.noSummary")}</span>
        </button>
      )) : <InlineEmptyState title={t("dataLab.empty")} description={t("dataLab.emptyBucketDescription")} />}
    </section>
  );
}

function OptimizationSection({
  catalog,
  catalogLoading,
  form,
  results,
  runMutation,
  setForm,
  setResultTarget,
  t,
}: {
  catalog?: OptimizationCatalogResponse;
  catalogLoading: boolean;
  form: {
    suiteLabel: string;
    optimizerNames: string;
    functionNames: string;
    dimension: string;
    epoch: string;
    popSize: string;
    runs: string;
    workers: string;
  };
  results: HistoryItem[];
  runMutation: UseMutationResult<ApiPayload, Error, void, unknown>;
  setForm: Dispatch<SetStateAction<typeof form>>;
  setResultTarget: (target: ResultTarget | null) => void;
  t: (key: string) => string;
}): JSX.Element {
  return (
    <div className="data-lab-section-grid">
      <Surface title={t("dataLab.optimizationSuite")} actions={<PlaySquare aria-hidden="true" />} tone="emphasis">
        {catalogLoading ? <LoadingState title={t("dataLab.loadingCatalog")} description={t("dataLab.loadingCatalogDescription")} /> : null}
        <div className="metric-strip">
          <MetricPill label={t("dataLab.optimizers")} value={catalog?.summary?.optimizer_count ?? "-"} />
          <MetricPill label={t("dataLab.functions")} value={catalog?.summary?.function_count ?? "-"} />
          <MetricPill label={t("dataLab.minimum")} value={`${catalog?.suite_requirements?.min_algorithms || 3}x${catalog?.suite_requirements?.min_functions || 3}x${catalog?.suite_requirements?.min_runs || 3}`} tone="warning" />
        </div>
        <div className="form-grid">
          <Field label={t("dataLab.suiteLabel")}>
            <input value={form.suiteLabel} onChange={(event) => setForm((current) => ({ ...current, suiteLabel: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.optimizers")}>
            <input value={form.optimizerNames} onChange={(event) => setForm((current) => ({ ...current, optimizerNames: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.functions")}>
            <input value={form.functionNames} onChange={(event) => setForm((current) => ({ ...current, functionNames: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.dimension")}>
            <input value={form.dimension} onChange={(event) => setForm((current) => ({ ...current, dimension: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.epoch")}>
            <input value={form.epoch} onChange={(event) => setForm((current) => ({ ...current, epoch: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.population")}>
            <input value={form.popSize} onChange={(event) => setForm((current) => ({ ...current, popSize: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.runs")}>
            <input value={form.runs} onChange={(event) => setForm((current) => ({ ...current, runs: event.target.value }))} />
          </Field>
          <Field label={t("dataLab.workers")}>
            <input value={form.workers} onChange={(event) => setForm((current) => ({ ...current, workers: event.target.value }))} />
          </Field>
        </div>
        <div className="action-row">
          <Button variant="primary" disabled={runMutation.isPending} loading={runMutation.isPending} onClick={() => runMutation.mutate()}>
            {t("dataLab.optimizationSuite")}
          </Button>
        </div>
        <PayloadPreview payload={runMutation.data} error={runMutation.error} empty={t("dataLab.optimizationEmpty")} t={t} />
      </Surface>
      <Surface title={t("dataLab.optimizationHistory")}>
        <div className="data-lab-result-list">
          {results.map((item) => (
            <button
              className="data-lab-result-row"
              key={item.id || item.run_id || item.title}
              type="button"
              onClick={() => {
                const target = resultTargetFromItem("optimization", item);
                if (target) {
                  setResultTarget(target);
                }
              }}
            >
              <span>optimization</span>
              <strong>{item.title || item.id}</strong>
              <Badge tone={statusTone(item.status)}>{item.status || "ready"}</Badge>
            </button>
          ))}
        </div>
        {!results.length ? <InlineEmptyState title={t("dataLab.noOptimizationResults")} description={t("dataLab.noOptimizationResultsDescription")} /> : null}
      </Surface>
    </div>
  );
}

function PayloadPreview({
  empty,
  error,
  payload,
  t,
}: {
  empty: string;
  error?: Error | null;
  payload?: unknown;
  t: (key: string) => string;
}): JSX.Element {
  if (error) {
    return <InlineErrorState title={t("dataLab.requestFailed")} description={error.message} />;
  }
  if (!payload) {
    return <InlineEmptyState title={t("dataLab.awaitingData")} description={empty} />;
  }
  return (
    <pre className="data-lab-json-preview">
      <code>{JSON.stringify(payload, null, 2).slice(0, 7000)}</code>
    </pre>
  );
}
