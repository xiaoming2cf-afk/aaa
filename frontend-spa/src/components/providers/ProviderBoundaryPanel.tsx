import { AlertTriangle, Ban, ClipboardCheck } from "lucide-react";
import { Badge, MetricPill, Surface } from "../ui";

export function ProviderBoundaryPanel({ workspaceId }: { workspaceId: string }): JSX.Element {
  return (
    <Surface
      actions={<Badge tone="warning">Current scope only</Badge>}
      description="This page documents the boundary of the current product build; it is not a provider operations dashboard."
      eyebrow="Unavailable Surface"
      span
      title="Runtime Provider Management Is Disabled"
      tone="warning"
    >
      <ProviderMetricStrip workspaceId={workspaceId} />
      <div className="list-stack">
        <WorkspaceScopeCard workspaceId={workspaceId} />
        <CurrentScopeCard />
        <RestrictionGrid />
        <WorkInsteadCard />
        <ProviderNextChecksTable />
      </div>
    </Surface>
  );
}

function ProviderMetricStrip({ workspaceId }: { workspaceId: string }): JSX.Element {
  return (
    <div className="metric-strip">
      <MetricPill label="Management" tone="warning" value="disabled" />
      <MetricPill label="Runtime health" tone="warning" value="not exposed" />
      <MetricPill label="Workspace" tone={workspaceId ? "info" : "warning"} value={workspaceId ? "selected" : "none"} />
    </div>
  );
}

function WorkspaceScopeCard({ workspaceId }: { workspaceId: string }): JSX.Element {
  return (
    <div className="list-card static-card">
      <div className="list-card-title">
        <strong>Workspace</strong>
        <Badge tone={workspaceId ? "info" : "warning"}>{workspaceId ? "Selected" : "Missing"}</Badge>
      </div>
      <p>{workspaceId || "No workspace selected."}</p>
    </div>
  );
}

function CurrentScopeCard(): JSX.Element {
  return (
    <div className="list-card static-card">
      <div className="list-card-title">
        <strong>Current scope</strong>
        <Badge tone="warning">Restricted</Badge>
      </div>
      <p>
        This product build keeps research runs, review gates, publishing, knowledge capture, and team library
        workflows. Runtime provider management is not available in the current product scope, and the product does
        not expose model-provider setup, runtime health, or bundle operations.
      </p>
    </div>
  );
}

function RestrictionGrid(): JSX.Element {
  return (
    <div className="detail-grid">
      <div className="list-card static-card inline-state-error" role="note">
        <div className="list-card-title">
          <strong>Restricted capabilities</strong>
          <Ban aria-hidden="true" size={18} />
        </div>
        <ul className="plain-list">
          <li>Model-provider setup is not available here.</li>
          <li>Runtime health checks are not exposed here.</li>
          <li>Bundle operations are not available here.</li>
        </ul>
      </div>
      <div className="list-card static-card inline-state" role="note">
        <div className="list-card-title">
          <strong>Operating boundary</strong>
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <p className="muted">
          Provider status cannot be inferred from this page. Treat all runtime-provider management as out of scope for this build.
        </p>
      </div>
    </div>
  );
}

function WorkInsteadCard(): JSX.Element {
  return (
    <div className="list-card static-card">
      <div className="list-card-title">
        <strong>Where to work instead</strong>
        <ClipboardCheck aria-hidden="true" size={18} />
      </div>
      <p>Use Research for queued runs, Quality for business-quality review, and Team Library for publication.</p>
    </div>
  );
}

function ProviderNextChecksTable(): JSX.Element {
  return (
    <div className="ops-table-scroll">
      <table className="ops-table">
        <thead>
          <tr>
            <th>Next check</th>
            <th>Surface</th>
            <th>Expected state</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Research generation</td>
            <td>Research</td>
            <td>Confirm queued runs and runtime availability there.</td>
          </tr>
          <tr>
            <td>Publication gate</td>
            <td>Quality</td>
            <td>Confirm business score and engineering gate before publishing.</td>
          </tr>
          <tr>
            <td>Published artifacts</td>
            <td>Team Library</td>
            <td>Browse records after explicit publication.</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
