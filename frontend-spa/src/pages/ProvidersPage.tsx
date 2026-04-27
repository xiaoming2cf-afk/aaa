import { ProviderBoundaryPanel } from "../components/providers";

type UseAppState = () => {
  workspaceId: string;
};

export function ProvidersPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();

  return (
    <div className="terminal-page workbench-providers">
      <ProviderBoundaryPanel workspaceId={workspaceId} />
    </div>
  );
}
