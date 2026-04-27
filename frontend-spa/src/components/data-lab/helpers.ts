import type { AgentMessage, LlmConfig, LlmFormState, StatusTone } from "./types";

export const EMPTY_LLM_FORM: LlmFormState = {
  enabled: false,
  base_url: "",
  api_key: "",
  clear_api_key: false,
  coder_model: "",
  reviewer_model: "",
  report_model: "",
  label: "",
};

export function workspaceFormState(workspace?: LlmConfig["workspace"]): LlmFormState {
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

export function humanInterventionRequired(message?: AgentMessage): boolean {
  return Boolean(message?.human_intervention?.required);
}

export function formatFallbackReason(reason?: string): string {
  return reason || "override_applied";
}

export function formatMaybeNumber(value?: number): string {
  return typeof value === "number" ? value.toFixed(3) : "-";
}

export function formatBytes(value?: number): string {
  if (typeof value !== "number") {
    return "-";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function artifactLabelFromPath(path?: string): string {
  if (!path) {
    return "";
  }
  const normalized = path.replace(/\\/g, "/").split("?")[0].split("#")[0];
  return normalized.split("/").filter(Boolean).pop() || "notebook.ipynb";
}

export function shortId(value?: string): string {
  return value ? value.slice(0, 8) : "none";
}

export function compactList(values?: string[], emptyLabel = "none"): string {
  return values?.length ? values.join(", ") : emptyLabel;
}

export function displayStatus(status?: string, fallback = "UNKNOWN"): string {
  return (status || fallback).replace(/_/g, " ").toUpperCase();
}

export function statusTone(status?: string): StatusTone {
  const value = (status || "").toLowerCase();
  if (!value || value === "unknown" || value === "no session" || value === "unset") {
    return "neutral";
  }
  if (value.includes("blocked") || value.includes("failed") || value.includes("error") || value.includes("denied") || value.includes("unavailable")) {
    return "danger";
  }
  if (
    value.includes("needs_human")
    || value.includes("fallback")
    || value.includes("pending")
    || value.includes("prepar")
    || value.includes("running")
    || value.includes("queued")
    || value.includes("review")
    || value.includes("draft")
    || value.includes("not ready")
    || value.includes("not prepared")
    || value.includes("checking")
  ) {
    return "warning";
  }
  if (
    value.includes("ready")
    || value.includes("configured")
    || value.includes("complete")
    || value.includes("saved")
    || value.includes("succeeded")
    || value.includes("success")
    || value.includes("done")
  ) {
    return "success";
  }
  return "neutral";
}

export function llmResolvedStatus(query: { isLoading: boolean; isError: boolean; data?: LlmConfig }): string {
  if (query.isLoading) {
    return "checking";
  }
  if (query.isError) {
    return "unavailable";
  }
  if (query.data?.resolved.ready) {
    return "ready";
  }
  if (query.data?.resolved.enabled) {
    return "not ready";
  }
  return "fallback";
}
