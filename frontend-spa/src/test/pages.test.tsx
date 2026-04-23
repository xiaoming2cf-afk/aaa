import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch } from "../api";
import { DataLabAgentPage } from "../pages/DataLabAgentPage";
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
            metrics: {
              arbiter_math_mode: "active",
            },
            candidate_drafts: [
              {
                draft_id: "D1-1",
                status: "approved",
                summary: "Adequate support.",
                metadata: {
                  arbiter: {
                    mode: "active",
                    utility: 0.51,
                    risk: 0.18,
                    evidence_support: 0.125,
                  },
                },
              },
              {
                draft_id: "D1-2",
                status: "approved",
                summary: "Stronger support and broader citations.",
                metadata: {
                  arbiter: {
                    mode: "active",
                    utility: 0.63,
                    risk: 0.11,
                    evidence_support: 0.25,
                  },
                },
              },
            ],
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
    expect(screen.getByText(/ARBITER Candidates/i)).toBeInTheDocument();
    expect(screen.getByText(/mode active \/ utility 0.63/i)).toBeInTheDocument();
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
          metadata: {
            arbiter: {
              mode: "active",
              recent_delivery_posteriors: [0.91],
            },
          },
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
              metadata: {
                arbiter: {
                  delivery_posterior: 0.91,
                },
              },
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
    expect(screen.getByText(/ARBITER Delivery Layer/i)).toBeInTheDocument();
    expect(screen.getByText(/Recent delivery posteriors: 0.910/i)).toBeInTheDocument();
  });

  test("DataLabAgentPage hydrates from query run id and surfaces human intervention and report preview", async () => {
    apiFetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === "/api/workspaces/ws-1/assets") {
        return {
          items: [
            {
              id: "asset-1",
              title: "agent-sample.csv",
              kind: "dataset_csv",
            },
          ],
        };
      }
      if (path === "/api/workspaces/ws-1/data-lab/history") {
        return {
          agent_sessions: [
            {
              id: "run-1",
              run_id: "run-1",
              title: "Deep linked session",
              status: "needs_human_intervention",
              summary: "Execution failed after automated repair attempts.",
            },
          ],
        };
      }
      if (path === "/api/workspaces/ws-1/data-lab/agent/llm-config") {
        if ((init?.method || "GET").toUpperCase() === "PUT") {
          return {
            workspace: {
              configured: true,
              enabled: true,
              base_url: "https://gateway.example/v1",
              api_key_configured: true,
              coder_model: "coder-a",
              reviewer_model: "reviewer-a",
              report_model: "report-a",
              label: "Scoped config",
            },
            environment: {
              enabled: false,
              ready: false,
              base_url_configured: false,
              api_key_configured: false,
              coder_model: "",
              reviewer_model: "",
              report_model: "",
            },
            resolved: {
              enabled: true,
              ready: true,
              source: "workspace",
              coder_model: "coder-a",
              reviewer_model: "reviewer-a",
              report_model: "report-a",
            },
          };
        }
        return {
          workspace: {
            configured: true,
            enabled: true,
            base_url: "https://gateway.example/v1",
            api_key_configured: true,
            coder_model: "coder-a",
            reviewer_model: "reviewer-a",
            report_model: "report-a",
            label: "Scoped config",
          },
          environment: {
            enabled: false,
            ready: false,
            base_url_configured: false,
            api_key_configured: false,
            coder_model: "",
            reviewer_model: "",
            report_model: "",
          },
          resolved: {
            enabled: true,
            ready: true,
            source: "workspace",
            coder_model: "coder-a",
            reviewer_model: "reviewer-a",
            report_model: "report-a",
          },
        };
      }
      if (path === "/api/workspaces/ws-1/data-lab/agent/sessions/run-1") {
        return {
          session: {
            run_id: "run-1",
            title: "Deep linked session",
            run_status: "needs_human_intervention",
            detail_path: "/app/data-lab-agent?run=run-1",
            executor: {
              active_mode: "subprocess_replay",
            },
            llm: {
              ready: true,
              source: "workspace",
              coder_model: "coder-a",
            },
            assets: [
              {
                title: "agent-sample.csv",
                profile: {
                  rows: 4,
                  columns: 4,
                  schema_fingerprint: "abc123def4567890",
                  candidate_targets: ["y"],
                  quality_warnings: ["Column x has potential numeric outliers."],
                },
              },
            ],
            cells: [{ id: "cell-1", status: "success" }],
            profile_snapshots: [{ id: "snap-1" }],
            safety_events: [{ at: "2026-04-23T10:00:00Z", message: "Blocked os.system." }],
            messages: [
              {
                id: "user-1",
                role: "user",
                content: "Plot a histogram of `missing_column`.",
              },
              {
                id: "assistant-1",
                role: "assistant",
                content: "Execution failed after automated repair attempts. Human code review is required.",
                status: "needs_human_intervention",
                code: "print(",
                execution_mode: "not_executed",
                human_intervention: {
                  required: true,
                  reason: "SyntaxError: '(' was never closed",
                  next_action: "Edit the generated Python cell and submit it as manual code.",
                },
                execution: {
                  error: "SyntaxError: '(' was never closed",
                },
                knowledge_cards: [
                  {
                    id: "card-1",
                    source_type: "workspace_knowledge",
                    title: "Use available columns",
                    summary: "The dataset contains y, x, and group.",
                  },
                ],
                llm_trace_summary: [
                  {
                    role: "coder",
                    source: "workspace",
                    summary: "Generated initial code plan.",
                  },
                ],
                repair_trace: [
                  {
                    attempt: 1,
                    status: "repair_requested",
                    error: "NameError: missing_column is not defined",
                    suggestion: "Use available columns instead.",
                  },
                ],
              },
            ],
          },
        };
      }
      if (path === "/api/workspaces/ws-1/data-lab/agent/sessions/run-1/report") {
        return {
          session: { run_id: "run-1" },
          report: {
            path: "/tmp/report.md",
            markdown: "# Deep linked session\n\n## Analysis Steps\n- Step 1",
          },
        };
      }
      if (path === "/api/workspaces/ws-1/data-lab/agent/sessions/run-1/messages") {
        return {
          session: {
            run_id: "run-1",
          },
        };
      }
      return {};
    });

    const useAppState = () => ({
      workspaceId: "ws-1",
    });

    renderWithQuery(
      <MemoryRouter initialEntries={["/data-lab-agent?run=run-1"]}>
        <Routes>
          <Route path="/data-lab-agent" element={<DataLabAgentPage useAppState={useAppState} />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: /Deep linked session/i })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("https://gateway.example/v1")).toBeInTheDocument();
    expect(screen.getAllByText(/Human intervention required/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Notebook/i })).toHaveAttribute("href", "/api/workspaces/ws-1/data-lab/agent/sessions/run-1/notebook");

    await userEvent.click(screen.getByRole("button", { name: /Edit Failed Code/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Optional Python code for human intervention/i)).toHaveValue("print(");
    });
    expect(screen.getByPlaceholderText(/Why this manual code is being used/i)).toHaveValue("Manual correction after automated repair failed.");

    await userEvent.click(screen.getByRole("button", { name: /Generate Report/i }));

    expect(await screen.findByText(/Generated Report/i)).toBeInTheDocument();
    expect(screen.getByText(/Analysis Steps/i)).toBeInTheDocument();
  });
});
