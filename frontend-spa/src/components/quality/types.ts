export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

export type QualityCheck = {
  key: string;
  label: string;
  passed?: boolean;
};

export type QualityDimension = {
  key: string;
  label: string;
  score?: number;
  checks?: QualityCheck[];
};

export type EngineeringGate = {
  passed?: boolean;
  checks?: QualityCheck[];
  source?: string;
};

export type QualityScorecard = {
  active_bundle?: unknown;
  blocking_reasons?: string[];
  business_deliverable?: boolean;
  deliverable?: boolean;
  dimensions?: QualityDimension[];
  engineering_gate?: EngineeringGate;
  metadata?: {
    arbiter?: {
      mode?: string;
      recent_delivery_posteriors?: number[];
      v2?: {
        recent_choices?: boolean[];
        recent_delivery_posteriors?: number[];
      };
    };
  };
  metrics?: Record<string, unknown>;
  total_score?: number;
};

export type QualityRunSnapshot = {
  blocked_reason?: string;
  citation_coverage?: number;
  metadata?: {
    arbiter?: {
      delivery_posterior?: number;
      v2?: {
        comparison?: {
          fallback_reason?: string;
        };
        delivery_posterior?: number;
      };
    };
  };
  publish_allowed?: boolean;
  review_block_precision?: number;
  run_id: string;
  status?: string;
  unsupported_claim_rate?: number;
};

export type GateRow = {
  key: string;
  label: string;
  score?: number;
  state?: boolean;
  summary: string;
};

