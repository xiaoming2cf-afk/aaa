import type { ReactNode } from "react";

const DATA_LAB_IDE_STYLES = `
.data-lab-ide {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(320px, 420px);
  gap: 12px;
  align-items: start;
}

.data-lab-ide-column {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.data-lab-ide-browser,
.data-lab-ide-inspector {
  position: sticky;
  top: 86px;
  max-height: calc(100vh - 112px);
  overflow: auto;
  scrollbar-gutter: stable;
}

.data-lab-ide-workspace {
  min-width: 0;
}

.data-lab-inspector {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.data-lab-tab-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.78);
}

.data-lab-tab {
  min-height: 34px;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--muted);
  background: transparent;
  font-weight: 850;
  cursor: pointer;
}

.data-lab-tab:hover,
.data-lab-tab:focus-visible {
  border-color: var(--border-strong);
  color: var(--ink);
  background: var(--surface-muted);
  outline: none;
}

.data-lab-tab-active {
  border-color: var(--border-strong);
  color: var(--text);
  background: #ffffff;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
}

.data-lab-tab-panels,
.data-lab-tab-panel {
  min-width: 0;
}

.data-lab-tab-panel[hidden] {
  display: none;
}

.data-lab-dataset-list {
  max-height: 230px;
  overflow: auto;
}

@media (max-width: 1280px) {
  .data-lab-ide {
    grid-template-columns: minmax(250px, 0.82fr) minmax(0, 1.18fr);
  }

  .data-lab-ide-inspector {
    grid-column: 1 / -1;
    position: static;
    max-height: none;
    overflow: visible;
  }
}

@media (max-width: 920px) {
  .data-lab-ide {
    grid-template-columns: 1fr;
  }

  .data-lab-ide-browser,
  .data-lab-ide-inspector {
    position: static;
    max-height: none;
    overflow: visible;
  }
}

@media (max-width: 620px) {
  .data-lab-tab-list {
    grid-template-columns: 1fr;
  }
}
`;

export function DataLabIdeLayout({
  browser,
  inspector,
  workspace,
}: {
  browser: ReactNode;
  inspector: ReactNode;
  workspace: ReactNode;
}): JSX.Element {
  return (
    <>
      <style>{DATA_LAB_IDE_STYLES}</style>
      <div className="data-lab-ide">
        <aside className="data-lab-ide-column data-lab-ide-browser" aria-label="Session and dataset browser">
          {browser}
        </aside>
        <main className="data-lab-ide-column data-lab-ide-workspace" aria-label="Message workspace">
          {workspace}
        </main>
        <aside className="data-lab-ide-column data-lab-ide-inspector" aria-label="Trace, notebook, and dataset inspector">
          {inspector}
        </aside>
      </div>
    </>
  );
}
