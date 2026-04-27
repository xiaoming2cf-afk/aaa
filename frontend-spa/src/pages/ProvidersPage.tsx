import { ProviderBoundaryPanel } from "../components/providers";

type UseAppState = () => {
  workspaceId: string;
};

export function ProvidersPage({ useAppState }: { useAppState: UseAppState }): JSX.Element {
  const { workspaceId } = useAppState();

  return (
    <div className="ops-grid">
      <ProviderBoundaryPanel workspaceId={workspaceId} />
    </div>
  );
}
