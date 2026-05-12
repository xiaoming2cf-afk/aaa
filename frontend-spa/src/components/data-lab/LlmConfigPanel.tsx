import type { Dispatch, SetStateAction } from "react";
import { RefreshCw, Save, TestTube } from "lucide-react";
import { InlineErrorState } from "../StatusPrimitives";
import { Badge, Button, Field, MetricPill, Surface } from "../ui";
import { displayStatus, statusTone } from "./helpers";
import type { LlmConfig, LlmFormState } from "./types";

function displayLlmStatus(value: string): string {
  const status = displayStatus(value);
  return status === "READY" ? "Configured" : status;
}

export function LlmConfigPanel({
  environmentLlmStatus,
  error,
  isError,
  llmConfig,
  llmForm,
  llmStatus,
  llmTestResult,
  onLoadStored,
  onSave,
  onTest,
  savePending,
  setLlmForm,
  testPending,
  workspaceId,
  workspaceLlmStatus,
}: {
  environmentLlmStatus: string;
  error?: Error | null;
  isError: boolean;
  llmConfig?: LlmConfig;
  llmForm: LlmFormState;
  llmStatus: string;
  llmTestResult: string;
  onLoadStored: () => void;
  onSave: () => void;
  onTest: () => void;
  savePending: boolean;
  setLlmForm: Dispatch<SetStateAction<LlmFormState>>;
  testPending: boolean;
  workspaceId: string;
  workspaceLlmStatus: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="LLM Config"
      title="Scoped Model Settings"
      description={(
        <>
          Resolved: <Badge tone={statusTone(llmStatus)}>{displayLlmStatus(llmStatus)}</Badge> via {llmConfig?.resolved.source || "none"}.
        </>
      )}
      actions={(
        <>
          <Button icon={<RefreshCw size={16} aria-hidden="true" />} variant="ghost" onClick={onLoadStored}>
            Load Stored
          </Button>
          <Button
            icon={<TestTube size={16} aria-hidden="true" />}
            variant="ghost"
            disabled={!workspaceId || testPending}
            onClick={onTest}
          >
            Test
          </Button>
          <Button
            icon={<Save size={16} aria-hidden="true" />}
            variant="primary"
            disabled={!workspaceId || savePending}
            onClick={onSave}
          >
            Save LLM Config
          </Button>
        </>
      )}
    >
      <div className="metric-strip" aria-label="LLM configuration state">
        <MetricPill label="Workspace" value={displayLlmStatus(workspaceLlmStatus)} tone={statusTone(workspaceLlmStatus)} />
        <MetricPill label="Environment" value={displayLlmStatus(environmentLlmStatus)} tone={statusTone(environmentLlmStatus)} />
        <MetricPill label="Resolved" value={displayLlmStatus(llmStatus)} tone={statusTone(llmStatus)} />
      </div>
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>Trusted execution boundary</strong>
          <Badge tone={llmConfig?.risk_summary?.trusted_execution_enabled ? "danger" : "warning"}>
            {llmConfig?.risk_summary?.trusted_execution_enabled ? "ENABLED" : "DISABLED"}
          </Badge>
        </div>
        <p className="muted">
          DATA_LAB_AGENT_ENABLED allows session creation. DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED controls Python code execution.
          Current sandbox claim: {llmConfig?.risk_summary?.sandbox_claim || "none"}.
        </p>
        <p className="muted">
          {llmConfig?.risk_summary?.warning_message || "Python execution is not sandboxed."} {llmConfig?.risk_summary?.production_guidance || "Keep trusted execution disabled unless an isolated worker or container is authorized."}
        </p>
      </div>
      <div className="form-grid">
        <Field label="Enable scoped LLM">
          <select
            value={llmForm.enabled ? "true" : "false"}
            onChange={(event) => setLlmForm((current) => ({ ...current, enabled: event.target.value === "true" }))}
          >
            <option value="false">Disabled</option>
            <option value="true">Enabled</option>
          </select>
        </Field>
        <Field label="Base URL">
          <input value={llmForm.base_url} onChange={(event) => setLlmForm((current) => ({ ...current, base_url: event.target.value }))} placeholder="https://gateway.example/v1" />
        </Field>
        <Field label="API Key">
          <input value={llmForm.api_key} onChange={(event) => setLlmForm((current) => ({ ...current, api_key: event.target.value }))} placeholder={llmConfig?.workspace.api_key_configured ? "Stored; leave blank to keep" : "Optional for local gateways"} />
        </Field>
        <Field label="Stored Key">
          <select
            value={llmForm.clear_api_key ? "clear" : "keep"}
            onChange={(event) => setLlmForm((current) => ({ ...current, clear_api_key: event.target.value === "clear" }))}
          >
            <option value="keep">Keep stored key</option>
            <option value="clear">Clear stored key</option>
          </select>
        </Field>
        <Field label="Label">
          <input value={llmForm.label} onChange={(event) => setLlmForm((current) => ({ ...current, label: event.target.value }))} placeholder="Workspace-scoped agent config" />
        </Field>
        <Field label="Coder Model">
          <input value={llmForm.coder_model} onChange={(event) => setLlmForm((current) => ({ ...current, coder_model: event.target.value }))} />
        </Field>
        <Field label="Reviewer Model">
          <input value={llmForm.reviewer_model} onChange={(event) => setLlmForm((current) => ({ ...current, reviewer_model: event.target.value }))} />
        </Field>
        <Field label="Report Model">
          <input value={llmForm.report_model} onChange={(event) => setLlmForm((current) => ({ ...current, report_model: event.target.value }))} />
        </Field>
      </div>
      {llmTestResult ? (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>LLM test result</strong>
            <Badge tone={statusTone(llmTestResult)}>{displayStatus(llmTestResult.split(":")[0])}</Badge>
          </div>
          <p className="muted">{llmTestResult}</p>
        </div>
      ) : null}
      {isError ? (
        <InlineErrorState title="LLM config could not load" description={error?.message || "The workspace LLM configuration request failed."} />
      ) : null}
    </Surface>
  );
}
