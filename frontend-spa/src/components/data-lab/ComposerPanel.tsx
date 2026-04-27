import type { RefObject } from "react";
import { Code, FileText, RefreshCw, RotateCcw, Send } from "lucide-react";
import { Badge, Button, Field, Surface } from "../ui";
import type { AgentMessage } from "./types";

export function ComposerPanel({
  executionMode,
  executionModeSelectRef,
  interventionNote,
  interventionNoteInputRef,
  latestAssistantWithCode,
  latestPrompt,
  manualCode,
  manualCodeInputRef,
  message,
  messageInputRef,
  needsHuman,
  onGenerateReport,
  onRetryLatestPrompt,
  onRunMessage,
  reportPending,
  selectedRunId,
  sendPending,
  setExecutionMode,
  setInterventionNote,
  setManualCode,
  setMessage,
}: {
  executionMode: string;
  executionModeSelectRef: RefObject<HTMLSelectElement>;
  interventionNote: string;
  interventionNoteInputRef: RefObject<HTMLInputElement>;
  latestAssistantWithCode?: AgentMessage;
  latestPrompt: string;
  manualCode: string;
  manualCodeInputRef: RefObject<HTMLTextAreaElement>;
  message: string;
  messageInputRef: RefObject<HTMLTextAreaElement>;
  needsHuman: boolean;
  onGenerateReport: () => void;
  onRetryLatestPrompt: () => void;
  onRunMessage: () => void;
  reportPending: boolean;
  selectedRunId: string;
  sendPending: boolean;
  setExecutionMode: (value: string) => void;
  setInterventionNote: (value: string) => void;
  setManualCode: (value: string) => void;
  setMessage: (value: string) => void;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Composer"
      title={manualCode.trim() ? "Manual Intervention Draft" : "Agent Instruction"}
      description={needsHuman ? "Human intervention is required before the agent can continue cleanly." : "Send a prompt or provide a reviewed Python override."}
    >
      {needsHuman ? (
        <div className="list-card static-card" role="alert">
          <div className="list-card-title">
            <strong>Human intervention required</strong>
            <Badge tone="warning">Review code</Badge>
          </div>
          <p>{latestAssistantWithCode?.human_intervention?.reason || "Automated repair could not complete this cell."}</p>
          {latestAssistantWithCode?.human_intervention?.next_action ? (
            <p className="muted">{latestAssistantWithCode.human_intervention.next_action}</p>
          ) : null}
          <div className="action-row">
            <Button
              icon={<Code size={16} aria-hidden="true" />}
              variant="ghost"
              onClick={() => {
                setManualCode(latestAssistantWithCode?.code || "");
                setInterventionNote("Manual correction after automated repair failed.");
              }}
            >
              Edit Failed Code
            </Button>
            <Button
              icon={<RotateCcw size={16} aria-hidden="true" />}
              variant="ghost"
              disabled={!latestPrompt || sendPending}
              onClick={onRetryLatestPrompt}
            >
              Retry Last Prompt
            </Button>
          </div>
        </div>
      ) : null}
      <div className="form-grid">
        <Field label="Instruction" span>
          <textarea ref={messageInputRef} value={message} onChange={(event) => setMessage(event.target.value)} rows={4} />
        </Field>
        <Field label="Execution Mode">
          <select ref={executionModeSelectRef} value={executionMode} onChange={(event) => setExecutionMode(event.target.value)}>
            <option value="">Session default</option>
            <option value="subprocess_replay">Trusted subprocess replay</option>
            <option value="auto">Auto dual mode</option>
            <option value="ipython_kernel">IPython kernel</option>
          </select>
        </Field>
        <Field label="Trusted state">
          <input value={executionMode ? "Explicit mode selected; review server policy before running." : "Session default; approval state is unknown until run."} readOnly />
        </Field>
        <Field label="Manual code override" span>
          <textarea ref={manualCodeInputRef} value={manualCode} onChange={(event) => setManualCode(event.target.value)} rows={8} placeholder="Optional Python code for human intervention." />
        </Field>
        <Field label="Human note" span>
          <input ref={interventionNoteInputRef} value={interventionNote} onChange={(event) => setInterventionNote(event.target.value)} placeholder="Why this manual code is being used." />
        </Field>
      </div>
      <div className="action-row">
        <Button
          icon={<Send size={16} aria-hidden="true" />}
          variant="primary"
          disabled={!selectedRunId || (!message.trim() && !manualCode.trim()) || sendPending}
          onClick={onRunMessage}
        >
          {manualCode.trim() ? "Run Manual Code" : "Run Message"}
        </Button>
        <Button
          icon={<RefreshCw size={16} aria-hidden="true" />}
          variant="ghost"
          disabled={!selectedRunId || sendPending || (!message.trim() && !manualCode.trim())}
          onClick={() => {
            setManualCode("");
            setInterventionNote("");
          }}
        >
          Clear Draft
        </Button>
        <Button
          icon={<FileText size={16} aria-hidden="true" />}
          variant="ghost"
          disabled={!selectedRunId || reportPending}
          onClick={onGenerateReport}
        >
          Generate Report
        </Button>
      </div>
    </Surface>
  );
}
