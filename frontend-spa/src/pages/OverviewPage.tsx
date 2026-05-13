import { Bot, BookOpen, FlaskConical, Search, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { InlineEmptyState } from "../components/StatusPrimitives";
import { Card, MetricCard, PageHeader, Surface } from "../components/ui";

type UseAppState = () => {
  workspaces: Array<{ id: string; name: string }>;
  teams: Array<{ id: string; name: string }>;
  workspaceId: string;
  teamId: string;
};

type WorkbenchSection = {
  description: string;
  label: string;
  title: string;
  to: string;
};

const workbenchSections: WorkbenchSection[] = [
  {
    description: "Start, review, and continue focused research runs.",
    label: "Open research",
    title: "Research",
    to: "/research",
  },
  {
    description: "Prepare structured datasets, run checks, and inspect outputs.",
    label: "Open Data Lab",
    title: "Data Lab",
    to: "/data-lab",
  },
  {
    description: "Keep notes, literature records, and reusable context close to the work.",
    label: "Open knowledge",
    title: "Knowledge",
    to: "/knowledge",
  },
  {
    description: "Check delivery readiness and review status before publishing.",
    label: "Open quality",
    title: "Quality",
    to: "/quality",
  },
];

export function OverviewPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaces, teams, workspaceId, teamId } = useAppState();
  const currentWorkspace = workspaces.find((workspace) => workspace.id === workspaceId);
  const currentTeam = teams.find((team) => team.id === teamId);
  const workspaceName = currentWorkspace?.name || "No workspace selected";
  const teamName = currentTeam?.name || "No team selected";

  if (!workspaceId || !currentWorkspace) {
    return (
      <div className="overview-page overview-page-redesign" aria-label="Workspace overview">
        <InlineEmptyState
          title="No workspace selected"
          description="Open a workspace or sign in before starting private research work."
          action={(
            <div className="action-row">
              <a className="button-link secondary-link" href="/workspace">Open workspace</a>
              <a className="button-link" href="/#auth-panel">Sign in</a>
            </div>
          )}
        />
      </div>
    );
  }

  return (
    <div className="overview-page overview-page-redesign" aria-label="Workspace overview">
      <Surface
        className="workspace-home-hero"
        title={(
          <PageHeader
            eyebrow="Workspace overview"
            title="Overview"
            description={`Current workspace: ${workspaceName}. Choose the next research action. Your workspace keeps runs, datasets, notes, and quality checks together.`}
          />
        )}
      >
        <div className="workspace-primary-actions" aria-label="Primary workspace actions">
          <Link className="ops-button ops-button-primary" to="/research">
            <span className="ops-button-icon" aria-hidden="true"><Search size={16} /></span>
            New research run
          </Link>
          <Link className="ops-button ops-button-secondary" to="/data-lab">
            <span className="ops-button-icon" aria-hidden="true"><FlaskConical size={16} /></span>
            Open Data Lab
          </Link>
          <Link className="ops-button ops-button-secondary" to="/data-lab-agent">
            <span className="ops-button-icon" aria-hidden="true"><Bot size={16} /></span>
            Start agent session
          </Link>
        </div>
      </Surface>

      <section className="workspace-metric-grid" aria-label="Workspace metrics">
        <MetricCard label="Workspace count" value={workspaces.length} />
        <MetricCard label="Team count" value={teams.length} />
        <MetricCard label="Current workspace" value={workspaceName} />
      </section>

      <section className="workspace-context-strip" aria-label="Current context">
        <span>Workspace: {workspaceName}</span>
        <span>Team context: {teamName}</span>
      </section>

      <section className="workspace-section-grid" aria-label="Workbench sections">
        {workbenchSections.map((section) => (
          <Card className="workspace-section-card" key={section.title}>
            <h3>{section.title}</h3>
            <p className="muted">{section.description}</p>
            <Link className="workspace-section-link" to={section.to}>
              {section.label}
            </Link>
          </Card>
        ))}
      </section>

      <Surface
        className="workspace-boundary-note"
        tone="warning"
        title="Agent execution remains separate."
        actions={<ShieldCheck aria-hidden="true" />}
      >
        <p className="muted">
          Data Lab Agent trusted execution is separate from the normal workspace and should remain disabled unless authorized.
        </p>
        <p className="muted">
          Use the standard Data Lab flow for structured dataset preparation, model checks, and result review.
        </p>
      </Surface>

      <Surface
        className="workspace-legacy-note"
        title="Need the legacy cockpit?"
        actions={<BookOpen aria-hidden="true" />}
      >
        <p className="muted">The legacy workspace remains available for older workflows while the SPA workbench evolves.</p>
        <a className="ops-button ops-button-ghost" href="/workspace">Open legacy workspace</a>
      </Surface>
    </div>
  );
}
