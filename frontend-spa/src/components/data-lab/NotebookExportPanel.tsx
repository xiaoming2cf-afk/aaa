import { Download, Link2, NotebookText } from "lucide-react";
import { ActionLink, Badge, Button, MetricPill, Surface } from "../ui";
import { shortId, statusTone } from "./helpers";

export function NotebookExportPanel({
  currentSessionReady,
  notebookArtifactLabel,
  notebookExportMessage,
  notebookExportSource,
  notebookExportState,
  notebookHref,
  notebookPending,
  onPrepareNotebook,
  permalinkHref,
  selectedRunId,
}: {
  currentSessionReady: boolean;
  notebookArtifactLabel: string;
  notebookExportMessage: string;
  notebookExportSource: string;
  notebookExportState: string;
  notebookHref: string;
  notebookPending: boolean;
  onPrepareNotebook: () => void;
  permalinkHref: string;
  selectedRunId: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Notebook Export"
      title="Evidence Package"
      description={notebookExportMessage}
      actions={(
        <>
          <Button
            icon={<NotebookText size={16} aria-hidden="true" />}
            variant="ghost"
            disabled={!selectedRunId || !currentSessionReady || notebookPending}
            aria-busy={notebookPending}
            aria-describedby="data-lab-notebook-status"
            onClick={onPrepareNotebook}
          >
            {notebookPending ? "Preparing Notebook" : "Prepare Notebook"}
          </Button>
          {notebookHref ? (
            <ActionLink icon={<Download size={16} aria-hidden="true" />} href={notebookHref} download variant="ghost">
              Download Notebook
            </ActionLink>
          ) : null}
          {permalinkHref ? (
            <ActionLink icon={<Link2 size={16} aria-hidden="true" />} href={permalinkHref} variant="ghost">
              Permalink
            </ActionLink>
          ) : null}
        </>
      )}
    >
      <div id="data-lab-notebook-status" className="metric-strip" role="status" aria-live="polite">
        <MetricPill label="Export" value={notebookHref ? "Prepared" : notebookPending ? "In progress" : selectedRunId ? "Pending" : "No session"} tone={statusTone(notebookExportState)} />
        <MetricPill label="Run" value={shortId(selectedRunId)} />
        <MetricPill label="Source" value={notebookExportSource} tone={notebookHref ? "success" : "neutral"} />
      </div>
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>Notebook artifact</strong>
          <Badge tone={statusTone(notebookExportState)}>{notebookExportState}</Badge>
        </div>
        <p>{notebookArtifactLabel || "No notebook artifact is available yet."}</p>
        <p className="muted">Source: {notebookExportSource}</p>
        {notebookArtifactLabel ? <p className="muted">Artifact: {notebookArtifactLabel}</p> : null}
        <p className="muted">Prepare Notebook creates the current export; Download Notebook appears only when the export path is available.</p>
      </div>
    </Surface>
  );
}
