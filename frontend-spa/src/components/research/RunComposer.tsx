import { Play } from "lucide-react";
import { Badge, Button, Field, MetricPill, Surface } from "../ui";
import type { BadgeTone } from "./types";
import { gateLabel, gateTone } from "./viewHelpers";

type RunComposerProps = {
  createErrorMessage?: string;
  createPending: boolean;
  draftVariants: string;
  instructions: string;
  mode: string;
  onDraftVariantsChange: (value: string) => void;
  onInstructionsChange: (value: string) => void;
  onModeChange: (value: string) => void;
  onQuestionChange: (value: string) => void;
  onStart: () => void;
  onTopicChange: (value: string) => void;
  question: string;
  runtimeCode?: string;
  runtimeDisabled: boolean;
  runtimeLabel: string;
  runtimeReady: boolean;
  runtimeStatus: string;
  runtimeTone: BadgeTone;
  topic: string;
  workspaceDeliverable?: boolean;
  workspaceId: string;
  workspaceScoreLabel: string;
};

export function RunComposer({
  createErrorMessage,
  createPending,
  draftVariants,
  instructions,
  mode,
  onDraftVariantsChange,
  onInstructionsChange,
  onModeChange,
  onQuestionChange,
  onStart,
  onTopicChange,
  question,
  runtimeCode,
  runtimeDisabled,
  runtimeLabel,
  runtimeReady,
  runtimeStatus,
  runtimeTone,
  topic,
  workspaceDeliverable,
  workspaceId,
  workspaceScoreLabel,
}: RunComposerProps): JSX.Element {
  return (
    <Surface
      actions={<Badge tone={runtimeTone}>{runtimeLabel}</Badge>}
      className="ops-col-5"
      description={workspaceDeliverable === true ? "Delivery gate passed." : "Delivery gate blocks publication until review reaches 100%."}
      eyebrow="Run Composer"
      title="Research Run"
      tone="emphasis"
    >
      <div className="metric-strip">
        <MetricPill label="Workspace Deliverable" tone={gateTone(workspaceDeliverable)} value={gateLabel(workspaceDeliverable)} />
        <MetricPill label="Score" tone={gateTone(workspaceDeliverable)} value={workspaceScoreLabel} />
        <MetricPill label="Drafts" value={draftVariants} />
      </div>

      <div className="form-grid">
        <Field label="Topic">
          <input value={topic} onChange={(event) => onTopicChange(event.target.value)} placeholder="Inflation persistence" />
        </Field>
        <Field label="Question">
          <input value={question} onChange={(event) => onQuestionChange(event.target.value)} placeholder="What explains inflation persistence?" />
        </Field>
        <Field label="Instructions" span>
          <textarea value={instructions} onChange={(event) => onInstructionsChange(event.target.value)} rows={4} />
        </Field>
        <Field label="Mode">
          <select value={mode} onChange={(event) => onModeChange(event.target.value)}>
            <option value="standard">standard</option>
            <option value="deep_research">deep_research</option>
          </select>
        </Field>
        <Field label="Draft Variants">
          <select value={draftVariants} onChange={(event) => onDraftVariantsChange(event.target.value)}>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
          </select>
        </Field>
      </div>

      <div className="action-row">
        <Button
          aria-describedby="research-runtime-status"
          disabled={!workspaceId || !topic || createPending || !runtimeReady}
          icon={<Play />}
          onClick={onStart}
          variant="primary"
        >
          Start Run
        </Button>
        <span id="research-runtime-status" className="muted">{createErrorMessage || runtimeStatus}</span>
      </div>

      {runtimeDisabled ? (
        <div className="list-card static-card inline-state-error" role="alert">
          <strong>Research runtime unavailable</strong>
          <p>{runtimeStatus}</p>
          {runtimeCode ? <p className="muted">Runtime code: {runtimeCode}</p> : null}
        </div>
      ) : null}
    </Surface>
  );
}

