export type ActiveWorkItem = {
  id: string;
  kind: "research_run" | "data_lab_session" | string;
  title: string;
  status?: string;
  summary?: string;
  href?: string;
  updated_at?: string;
  blocker_count?: number;
};

export type WorkbenchBlocker = {
  id?: string;
  resource_type?: string;
  resource_id?: string;
  source?: string;
  title?: string;
  severity?: "info" | "warning" | "danger" | string;
  reason?: string;
  blocking_reasons?: string[];
  href?: string;
  detail_path?: string;
};

export type PublishQueueItem = {
  id?: string;
  resource_type?: string;
  resource_id?: string;
  title: string;
  summary?: string;
  target?: string;
  status?: string;
  href?: string;
  detail_path?: string;
  publish_allowed?: boolean;
  blocking_reasons?: string[];
};

export type WorkbenchActivity = {
  id?: string;
  activity_type?: string;
  resource_id?: string;
  at?: string;
  occurred_at?: string;
  label?: string;
  title?: string;
  detail?: string;
  summary?: string;
  status?: string;
  href?: string;
  detail_path?: string;
};

export type WorkbenchAgentRun = {
  id: string;
  topic?: string;
  title?: string;
  question?: string;
  review_summary?: string;
  status?: string;
  current_stage?: string;
  queue_status?: string;
  blocking_reasons?: string[];
  detail_path?: string;
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
};

export type WorkbenchDataLabSession = {
  id?: string;
  run_id?: string;
  title?: string;
  status?: string;
  run_status?: string;
  summary?: string;
  detail_path?: string;
  created_at?: string;
  updated_at?: string;
  finished_at?: string;
};

export type RuntimeSummary = {
  research_runtime?: {
    enabled?: boolean;
    code?: string;
    message?: string;
  };
  provider_management?: {
    enabled?: boolean;
    message?: string;
  };
  quality?: {
    deliverable?: boolean;
    total_score?: number;
    blocked_count?: number;
    engineering_gate_passed?: boolean;
  };
  team?: {
    team_id?: string;
    attached?: boolean;
    library_count?: number;
    blocking_reasons?: string[];
  };
  counts?: {
    active_runs?: number;
    data_lab_sessions?: number;
    publish_queue?: number;
  };
  data_lab_agent?: {
    enabled?: boolean;
    trusted_execution_enabled?: boolean;
  };
};

export type WorkbenchOverview = {
  active_runs?: WorkbenchAgentRun[];
  data_lab_sessions?: WorkbenchDataLabSession[];
  active_work?: ActiveWorkItem[];
  quality_blockers?: WorkbenchBlocker[];
  publish_queue?: PublishQueueItem[];
  recent_activity?: WorkbenchActivity[];
  runtime_summary?: RuntimeSummary;
};
