type UseAppState = () => {
  workspaceId: string;
};

export function ProvidersPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();

  return (
    <div className="page-grid">
      <section className="panel panel-emphasis panel-span">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Unavailable Surface</p>
            <h3>Runtime Provider Management Is Disabled</h3>
          </div>
        </div>
        <div className="list-stack">
          <div className="list-card static-card">
            <strong>Workspace</strong>
            <p>{workspaceId || "No workspace selected."}</p>
          </div>
          <div className="list-card static-card">
            <strong>Current scope</strong>
            <p>
              This product build keeps research runs, review gates, publishing, knowledge capture, and team library
              workflows. Runtime provider management is not available in the current product scope, and the product does
              not expose model-provider setup, runtime health, or bundle operations.
            </p>
          </div>
          <div className="list-card static-card">
            <strong>Where to work instead</strong>
            <p>Use Research for queued runs, Quality for business-quality review, and Team Library for publication.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
