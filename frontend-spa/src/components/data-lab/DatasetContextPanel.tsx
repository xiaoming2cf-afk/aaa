import { Badge, JsonBlock, MetricPill, Surface } from "../ui";
import { compactList } from "./helpers";
import type { DatasetAsset, DatasetProfile } from "./types";

export function DatasetContextPanel({
  firstAsset,
  firstProfile,
  previewColumns,
}: {
  firstAsset?: DatasetAsset;
  firstProfile?: DatasetProfile;
  previewColumns: string[];
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Dataset Context"
      title={firstAsset?.title || "No dataset selected"}
      description={firstProfile ? `${firstProfile.rows || 0} rows, ${firstProfile.columns || 0} columns.` : "Session profile details appear after a dataset is attached."}
    >
      <div className="metric-strip" aria-label="Dataset profile metrics">
        <MetricPill label="Rows" value={firstProfile?.rows ?? "-"} />
        <MetricPill label="Columns" value={firstProfile?.columns ?? "-"} />
        <MetricPill label="Warnings" value={firstProfile?.quality_warnings?.length || 0} tone={firstProfile?.quality_warnings?.length ? "warning" : "neutral"} />
      </div>
      <div className="list-card static-card">
        <div className="list-card-title">
          <strong>Profile guidance</strong>
          <Badge tone={firstProfile ? "info" : "neutral"}>{firstProfile ? "PROFILED" : "UNKNOWN"}</Badge>
        </div>
        <p className="muted">Suggested targets: {compactList(firstProfile?.candidate_targets)}.</p>
        <p className="muted">Candidate features: {compactList(firstProfile?.candidate_features?.slice(0, 10))}.</p>
        {firstProfile?.schema_fingerprint ? (
          <p className="muted">Fingerprint: {firstProfile.schema_fingerprint}.</p>
        ) : null}
      </div>
      {firstProfile?.quality_warnings?.length ? (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Quality warnings</strong>
            <Badge tone="warning">{firstProfile.quality_warnings.length}</Badge>
          </div>
          <ul>
            {firstProfile.quality_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="list-card static-card">
          <div className="list-card-title">
            <strong>Quality warnings</strong>
            <Badge tone={firstProfile ? "neutral" : "warning"}>{firstProfile ? "NONE" : "UNKNOWN"}</Badge>
          </div>
          <p className="muted">{firstProfile ? "No major quality warnings detected in the initial profile." : "No profile has been returned for this session yet."}</p>
        </div>
      )}
      {firstProfile?.preview_rows?.length ? (
        <details className="list-card static-card">
          <summary>Profile Preview</summary>
          <table className="ops-table">
            <thead>
              <tr>
                {previewColumns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {firstProfile.preview_rows.slice(0, 5).map((row, rowIndex) => (
                <tr key={`preview-${rowIndex}`}>
                  {previewColumns.map((column) => (
                    <td key={`${rowIndex}-${column}`}>{String(row[column] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      <details className="list-card static-card">
        <summary>Raw profile</summary>
        <JsonBlock value={firstProfile || {}} />
      </details>
    </Surface>
  );
}
