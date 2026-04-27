export type KnowledgeRecord = {
  id: string;
  title: string;
  content?: string;
  content_excerpt?: string;
  publish_allowed?: boolean;
  blocking_reasons?: string[];
  tags?: string[];
  source_type?: string;
  created_at?: string;
  updated_at?: string;
  published_at?: string;
  metadata?: Record<string, unknown>;
  delivery_review?: {
    deliverable?: boolean;
    publish_allowed?: boolean;
    total_score?: number;
    blocking_reasons?: string[];
  };
};

export function formatDate(value?: string): string {
  if (!value) {
    return "not recorded";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function metadataValue(record: KnowledgeRecord, key: string): string {
  const value = record.metadata?.[key];
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

export function sourceType(record: KnowledgeRecord): string {
  return record.source_type || metadataValue(record, "source_type") || "workspace_note";
}

export function sourceLabel(record: KnowledgeRecord): string {
  return metadataValue(record, "source") || "spa";
}

export function blockingReasons(record: KnowledgeRecord): string[] {
  return record.blocking_reasons?.length
    ? record.blocking_reasons
    : record.delivery_review?.blocking_reasons || [];
}
