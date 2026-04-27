import type { RefObject } from "react";
import { ExternalLink, Play } from "lucide-react";
import { InlineEmptyState, InlineErrorState } from "../StatusPrimitives";
import { ActionLink, Badge, Button, Field, Surface } from "../ui";
import type { AssetSummary } from "./types";

export function SessionLaunchPanel({
  assetId,
  assetsError,
  assetsSuccess,
  createPending,
  datasetAssets,
  datasetSelectRef,
  onCreateSession,
  permalinkHref,
  setAssetId,
  setTitle,
  title,
  titleInputRef,
  workspaceId,
}: {
  assetId: string;
  assetsError?: Error | null;
  assetsSuccess: boolean;
  createPending: boolean;
  datasetAssets: AssetSummary[];
  datasetSelectRef: RefObject<HTMLSelectElement>;
  onCreateSession: (payload: { nextTitle: string; nextAssetId: string }) => void;
  permalinkHref: string;
  setAssetId: (value: string) => void;
  setTitle: (value: string) => void;
  title: string;
  titleInputRef: RefObject<HTMLInputElement>;
  workspaceId: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-4"
      eyebrow="Session Launch"
      title="Start Analysis Session"
      tone="emphasis"
      description="Launch an agent session against a registered dataset while keeping trusted execution explicit."
      actions={(
        permalinkHref ? (
          <ActionLink href={permalinkHref} icon={<ExternalLink size={16} aria-hidden="true" />} variant="ghost">
            Open Session Link
          </ActionLink>
        ) : null
      )}
    >
      <div className="list-card static-card risk-notice" role="note" aria-label="Trusted mode risk notice">
        <div className="list-card-title">
          <strong>Trusted mode notice</strong>
          <Badge tone="warning">Requires approval</Badge>
        </div>
        <p className="muted">
          Python execution can read files and use network access available to the server process. Keep trusted execution disabled unless the deployment, datasets, and users are approved for local code execution.
        </p>
        <p className="muted">
          Unknown, blocked, or unverified execution states are treated as not approved; they are never shown as passed.
        </p>
      </div>
      <div className="form-grid">
        <Field label="Session Title">
          <input ref={titleInputRef} value={title} onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label="Dataset">
          <select ref={datasetSelectRef} value={assetId} onChange={(event) => setAssetId(event.target.value)}>
            <option value="">Select dataset</option>
            {datasetAssets.map((asset) => (
              <option key={asset.id} value={asset.id}>{asset.title}</option>
            ))}
          </select>
        </Field>
      </div>
      <div className="action-row">
        <Button
          icon={<Play size={16} aria-hidden="true" />}
          variant="primary"
          disabled={!workspaceId || !assetId || createPending}
          onClick={() => {
            const nextTitle = titleInputRef.current?.value ?? title;
            const nextAssetId = datasetSelectRef.current?.value ?? assetId;
            setTitle(nextTitle);
            setAssetId(nextAssetId);
            onCreateSession({ nextTitle, nextAssetId });
          }}
        >
          Create Session
        </Button>
        <span className="muted">Feature flag required: DATA_LAB_AGENT_ENABLED=true.</span>
      </div>
      {assetsError ? (
        <InlineErrorState title="Datasets could not load" description={assetsError.message} />
      ) : null}
      {!assetsError && assetsSuccess && !datasetAssets.length ? (
        <InlineEmptyState title="No datasets available" description="Upload or register a dataset asset before creating a Data Lab Agent session." />
      ) : null}
    </Surface>
  );
}
