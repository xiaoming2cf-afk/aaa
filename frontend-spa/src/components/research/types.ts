export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

export type RunSummary = {
  id: string;
  topic: string;
  status: string;
  current_stage: string;
  queue_status: string;
  review_summary: string;
  quality_summary?: { quality_score?: number };
  publish_allowed?: boolean;
  blocking_reasons?: string[];
  delivery_review?: {
    deliverable?: boolean;
    publish_allowed?: boolean;
    blocking_reasons?: string[];
  };
};

export type RunDetail = RunSummary & {
  attachments?: Array<Record<string, unknown>>;
  candidate_drafts?: Array<any>;
  delivery_review?: RunSummary["delivery_review"] & Record<string, unknown>;
  evidence?: unknown;
  final_text?: string;
  metrics?: Record<string, any>;
  review?: unknown;
  trace?: unknown;
};

export type ResearchRuntimeCapability = {
  research_runtime: {
    enabled: boolean;
    code: string;
    message: string;
    trace?: Record<string, unknown>;
  };
};

export type ResearchTeam = {
  id: string;
  name: string;
};

export type RunDetailTab = "overview" | "evidence" | "review" | "arbiter" | "report";

