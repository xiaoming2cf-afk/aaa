import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { apiFetch } from "../api";
import { KnowledgePage } from "../pages/KnowledgePage";
import { QualityPage } from "../pages/QualityPage";
import { ResearchPage } from "../pages/ResearchPage";

vi.mock("../api", () => ({
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);

function renderWithQuery(ui: JSX.Element): void {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("SPA delivery gating", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  test("ResearchPage disables publish when delivery review blocks the run", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/workspaces/ws-1/research/runs") {
        return {
          items: [
            {
              id: "run-1",
              topic: "Blocked Run",
              status: "saved",
              current_stage: "saved",
              queue_status: "completed",
              review_summary: "Blocked by delivery review",
              publish_allowed: false,
              blocking_reasons: ["Business scorecard is not yet 500/500."],
            },
          ],
        };
      }
      if (path === "/api/workspaces/ws-1/quality/scorecard") {
        return {
          total_score: 400,
          deliverable: false,
          metrics: {},
        };
      }
      if (path === "/api/workspaces/ws-1/research/runs/run-1") {
        return {
          run: {
            id: "run-1",
            evidence: {},
            review: {},
            trace: [],
            final_text: "# Report",
            publish_allowed: false,
            blocking_reasons: ["Business scorecard is not yet 500/500."],
            delivery_review: {
              publish_allowed: false,
              blocking_reasons: ["Business scorecard is not yet 500/500."],
            },
          },
          eval_candidate: null,
        };
      }
      return {};
    });

    const useAppState = () => ({
      workspaceId: "ws-1",
      teamId: "team-1",
      teams: [{ id: "team-1", name: "Team One" }],
    });

    renderWithQuery(<ResearchPage useAppState={useAppState} />);
    await userEvent.click(await screen.findByRole("button", { name: /Blocked Run/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Publish to Team Library/i })).toBeDisabled();
    });
    expect(screen.getByText(/Publish is blocked/i)).toBeInTheDocument();
  });

  test("KnowledgePage disables publish when the knowledge record is not deliverable", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/workspaces/ws-1/knowledge") {
        return {
          items: [
            {
              id: "record-1",
              title: "Blocked note",
              content_excerpt: "Needs provenance.",
              publish_allowed: false,
              blocking_reasons: ["Source metadata or provenance is present: failed"],
            },
          ],
        };
      }
      return {};
    });

    const useAppState = () => ({
      workspaceId: "ws-1",
      teamId: "team-1",
      teams: [{ id: "team-1", name: "Team One" }],
    });

    renderWithQuery(<KnowledgePage useAppState={useAppState} />);

    expect(await screen.findByText(/Needs provenance/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish/i })).toBeDisabled();
  });

  test("QualityPage shows business and engineering gate results together", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/workspaces/ws-1/quality/scorecard") {
        return {
          total_score: 500,
          deliverable: false,
          business_deliverable: true,
          blocking_reasons: ["Backend pytest suite passes: failed"],
          dimensions: [
            {
              key: "workflow_integrity",
              label: "Workflow Integrity",
              score: 100,
              checks: [{ key: "recent_runs_present", label: "Recent research runs exist", passed: true }],
            },
          ],
          engineering_gate: {
            passed: false,
            checks: [
              {
                key: "backend_tests_green",
                label: "Backend pytest suite passes",
                passed: false,
                detail: "failed",
              },
            ],
          },
        };
      }
      if (path === "/api/workspaces/ws-1/quality/runs") {
        return {
          items: [
            {
              run_id: "run-1",
              status: "saved",
              citation_coverage: 1,
              unsupported_claim_rate: 0,
              review_block_precision: 1,
              blocked_reason: "",
            },
          ],
        };
      }
      return {};
    });

    const useAppState = () => ({
      workspaceId: "ws-1",
    });

    renderWithQuery(<QualityPage useAppState={useAppState} />);

    expect(await screen.findByText(/^Engineering Gate$/i)).toBeInTheDocument();
    expect(await screen.findByText(/Backend pytest suite passes: failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Workspace Deliverable/i)).toBeInTheDocument();
    expect(screen.getByText(/Business gate: PASS \/ Engineering gate: FAIL/i)).toBeInTheDocument();
  });
});
