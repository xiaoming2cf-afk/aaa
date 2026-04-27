import type { BadgeTone, QualityCheck, QualityDimension } from "./types";

const SUCCESS_STATUSES = new Set(["saved", "completed", "approved", "passed", "pass"]);
const DANGER_STATUSES = new Set(["blocked", "failed", "error", "rejected", "fail"]);
const ACTIVE_STATUSES = new Set(["queued", "running", "pending", "drafting", "reviewing", "in_progress"]);

export function normalizeStatus(value?: string): string {
  return (value || "unknown").toLowerCase();
}

export function statusTone(value?: string): BadgeTone {
  const normalized = normalizeStatus(value);
  if (SUCCESS_STATUSES.has(normalized)) return "success";
  if (DANGER_STATUSES.has(normalized)) return "danger";
  if (ACTIVE_STATUSES.has(normalized)) return "info";
  return "warning";
}

export function gateTone(value: boolean | undefined): BadgeTone {
  if (value === true) return "success";
  if (value === false) return "danger";
  return "warning";
}

export function gateLabel(value: boolean | undefined, falseLabel = "FAIL"): string {
  if (value === true) return "PASS";
  if (value === false) return falseLabel;
  return "UNKNOWN";
}

export function boolValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

export function checkSummary(checks: QualityCheck[] = []): string {
  if (!checks.length) return "No checks returned.";
  const passed = checks.filter((check) => check.passed === true).length;
  return `${passed}/${checks.length} checks passed`;
}

export function dimensionGateState(dimension: QualityDimension): boolean | undefined {
  const hasScore = typeof dimension.score === "number";
  const checks = dimension.checks || [];
  if (!hasScore && !checks.length) return undefined;
  if (checks.length) return checks.every((check) => check.passed === true) && Number(dimension.score ?? 0) >= 100;
  return Number(dimension.score ?? 0) >= 100;
}

