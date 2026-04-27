import { useState, type ReactNode } from "react";

type InspectorTabId = "trace" | "notebook" | "dataset";

const INSPECTOR_TABS: Array<{
  id: InspectorTabId;
  label: string;
}> = [
  { id: "trace", label: "Trace" },
  { id: "notebook", label: "Notebook" },
  { id: "dataset", label: "Dataset" },
];

export function InspectorTabsPanel({
  dataset,
  initialTab = "notebook",
  notebook,
  trace,
}: {
  dataset: ReactNode;
  initialTab?: InspectorTabId;
  notebook: ReactNode;
  trace: ReactNode;
}): JSX.Element {
  const [activeTab, setActiveTab] = useState<InspectorTabId>(initialTab);

  return (
    <section className="data-lab-inspector" aria-label="Data Lab inspector">
      <div className="data-lab-tab-list" role="tablist" aria-label="Trace, notebook, and dataset tabs">
        {INSPECTOR_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              aria-controls={`data-lab-${tab.id}-panel`}
              aria-selected={isActive}
              className={`data-lab-tab ${isActive ? "data-lab-tab-active" : ""}`.trim()}
              id={`data-lab-${tab.id}-tab`}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="data-lab-tab-panels">
        <div
          aria-labelledby="data-lab-trace-tab"
          className="data-lab-tab-panel"
          hidden={activeTab !== "trace"}
          id="data-lab-trace-panel"
          role="tabpanel"
        >
          {trace}
        </div>
        <div
          aria-labelledby="data-lab-notebook-tab"
          className="data-lab-tab-panel"
          hidden={activeTab !== "notebook"}
          id="data-lab-notebook-panel"
          role="tabpanel"
        >
          {notebook}
        </div>
        <div
          aria-labelledby="data-lab-dataset-tab"
          className="data-lab-tab-panel"
          hidden={activeTab !== "dataset"}
          id="data-lab-dataset-panel"
          role="tabpanel"
        >
          {dataset}
        </div>
      </div>
    </section>
  );
}
