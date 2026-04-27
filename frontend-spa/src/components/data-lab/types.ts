export type AssetSummary = {
  id: string;
  title: string;
  kind: string;
};

export type KnowledgeCard = {
  id: string;
  source_type: string;
  title: string;
  summary: string;
  score?: number;
  tags?: string[];
};

export type AgentMessage = {
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

export type AgentSession = {
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

export type DatasetAsset = NonNullable<AgentSession["assets"]>[number];
export type DatasetProfile = NonNullable<DatasetAsset["profile"]>;

export type LlmConfig = {
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

export type HistoryItem = {
  id: string;
  run_id?: string;
  title: string;
  status: string;
  summary?: string;
};

export type LlmFormState = {
  enabled: boolean;
  base_url: string;
  api_key: string;
  clear_api_key: boolean;
  coder_model: string;
  reviewer_model: string;
  report_model: string;
  label: string;
};

export type SendMessageInput = {
  message: string;
  userCode: string;
  interventionNote: string;
  executionMode: string;
};

export type ReportResponse = {
  session: AgentSession;
  report: {
    path: string;
    markdown: string;
  };
};

export type NotebookResponse = {
  session: AgentSession;
  notebook: {
    path: string;
    download_path: string;
  };
};

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";
