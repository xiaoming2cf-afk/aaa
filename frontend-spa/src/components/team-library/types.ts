export type TeamLibraryRecord = {
  id: string;
  title: string;
  summary?: string;
  source_type?: string;
  created_at?: string;
  updated_at?: string;
  published_at?: string;
  metadata?: Record<string, unknown>;
};

export function formatDate(value?: string): string {
  if (!value) {
    return "not recorded";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function metadataString(item: TeamLibraryRecord, key: string): string {
  const value = item.metadata?.[key];
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}
