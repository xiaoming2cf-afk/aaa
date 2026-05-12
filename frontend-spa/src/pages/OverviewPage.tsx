import { BarChart3, BookOpen, Bot, FlaskConical, Library, Search, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { InlineEmptyState } from "../components/StatusPrimitives";
import { Card, MetricCard, PageHeader, Surface } from "../components/ui";

type UseAppState = () => {
  workspaces: Array<{ id: string; name: string }>;
  teams: Array<{ id: string; name: string }>;
  workspaceId: string;
  teamId: string;
};

type QuickEntry = {
  description: string;
  href?: string;
  label: string;
  title: string;
  to?: string;
  icon: JSX.Element;
};

export function OverviewPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaces, teams, workspaceId, teamId } = useAppState();
  const currentWorkspace = workspaces.find((workspace) => workspace.id === workspaceId);
  const currentTeam = teams.find((team) => team.id === teamId);
  const workspaceName = currentWorkspace?.name || "No workspace selected";
  const teamName = currentTeam?.name || "No team selected";
  const quickEntries: QuickEntry[] = [
    {
      description: "Open the research run queue and drafting workflow.",
      icon: <Search aria-hidden="true" />,
      label: "Runs",
      title: "Research Runs",
      to: "/research",
    },
    {
      description: "Open the Data Lab hub for dataset and model workflows.",
      icon: <FlaskConical aria-hidden="true" />,
      label: "Workbench",
      title: "Data Lab",
      to: "/data-lab",
    },
    {
      description: "Launch the agentic analysis runtime for dataset conversations.",
      icon: <Bot aria-hidden="true" />,
      label: "Agent",
      title: "Data Lab Agent",
      to: "/data-lab-agent",
    },
    {
      description: "Review workspace notes, records, and reusable context.",
      icon: <BookOpen aria-hidden="true" />,
      label: "Memory",
      title: "Knowledge",
      to: "/knowledge",
    },
    {
      description: "Check delivery gates before publishing artifacts.",
      icon: <ShieldCheck aria-hidden="true" />,
      label: "Gates",
      title: "Quality",
      to: "/quality",
    },
    {
      description: "Open the legacy workspace cockpit outside the SPA shell.",
      href: "/workspace",
      icon: <Library aria-hidden="true" />,
      label: "Legacy",
      title: "Legacy Workspace",
    },
  ];

  if (!workspaceId || !currentWorkspace) {
    return (
      <div className="overview-page" aria-label="Workspace overview">
        <InlineEmptyState
          title="No workspace selected"
          description="Select or create a workspace from /workspace, or sign in again from /#auth-panel."
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
    <div className="overview-page" aria-label="Workspace overview">
      <Surface
        className="overview-summary"
        tone="emphasis"
        title={(
          <PageHeader
            eyebrow="Workspace Command Center"
            title="Overview"
            description={`Current workspace: ${workspaceName}. Team context: ${teamName}.`}
          />
        )}
      >
        <div className="overview-stat-grid" aria-label="Workspace counts">
          <MetricCard label="Workspace count" value={workspaces.length} />
          <MetricCard label="Team count" value={teams.length} />
          <MetricCard label="Current workspace" value={workspaceId ? 1 : 0} />
        </div>
      </Surface>

      <section className="overview-card-grid" aria-label="Quick entries">
        {quickEntries.map((entry) => (
          <OverviewCard key={entry.title} entry={entry} />
        ))}
      </section>

      <Surface
        eyebrow="Data Lab Boundary"
        title="Structured data stays separate from agent execution."
        actions={<BarChart3 aria-hidden="true" />}
      >
        <p className="muted">
          Data Lab is for dataset intake, preparation, modeling, results, and history. Data Lab Agent is the
          agentic analysis runtime, and trusted Python execution remains a separate gated capability.
        </p>
      </Surface>
    </div>
  );
}

function OverviewCard({ entry }: { entry: QuickEntry }): JSX.Element {
  const content = (
    <Card className="overview-card__body">
      <span className="overview-card-icon">{entry.icon}</span>
      <span className="overview-card-label">{entry.label}</span>
      <strong>{entry.title}</strong>
      <span>{entry.description}</span>
    </Card>
  );

  if (entry.href) {
    return (
      <a className="overview-card" href={entry.href}>
        {content}
      </a>
    );
  }
  return (
    <Link className="overview-card" to={entry.to || "/overview"}>
      {content}
    </Link>
  );
}
