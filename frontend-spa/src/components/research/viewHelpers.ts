import type { BadgeTone } from "./types";

const FINISHED_RUN_STATUSES = new Set(["saved", "completed", "approved"]);
const BLOCKED_RUN_STATUSES = new Set(["blocked", "failed", "error", "cancelled", "rejected"]);
const ACTIVE_RUN_STATUSES = new Set(["queued", "running", "pending", "drafting", "reviewing", "in_progress"]);

export function normalizeStatus(value?: string): string {
  return (value || "unknown").toLowerCase();
}

export function statusTone(value?: string): BadgeTone {
  const normalized = normalizeStatus(value);
  if (FINISHED_RUN_STATUSES.has(normalized)) return "success";
  if (BLOCKED_RUN_STATUSES.has(normalized)) return "danger";
  if (ACTIVE_RUN_STATUSES.has(normalized)) return "info";
  return "warning";
}

export function gateTone(value: boolean | undefined): BadgeTone {
  if (value === true) return "success";
  if (value === false) return "danger";
  return "warning";
}

export function gateLabel(value: boolean | undefined, blockedLabel = "BLOCKED"): string {
  if (value === true) return "PASS";
  if (value === false) return blockedLabel;
  return "UNKNOWN";
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

export function firstBlocker(reasons: string[], fallback: string): string {
  return reasons.find((reason) => Boolean(reason?.trim())) || fallback;
}

