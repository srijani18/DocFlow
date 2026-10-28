import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { WorkspaceMetrics } from "@/lib/api/metrics";
import { routeFetch } from "@/test/fetch-router";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { duration, MetricsView, usd } from "./metrics-view";

const supabase = createSupabaseMock();

vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const WORKSPACE_ID = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";
const ME = {
  user: {
    id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1",
    email: "ada@example.com",
    display_name: null,
  },
  memberships: [{ workspace: { id: WORKSPACE_ID, name: "Ada's workspace" }, role: "reviewer" }],
};
const OUTCOMES = { ok: 0, error: 0, invalid_output: 0, cache_hit: 0, skipped: 0 };
const IDLE_TASK = {
  calls: 0,
  outcomes: OUTCOMES,
  fallback_rate: null,
  served_by: [],
  latency_ms_p50: null,
};

const EMPTY: WorkspaceMetrics = {
  period: "30d",
  since: "2025-12-12T00:00:00Z",
  headline: {
    approved: 0,
    approved_without_edits: 0,
    approved_by_agent: 0,
    approved_without_edits_rate: null,
    fields_reviewed: 0,
    fields_unchanged: 0,
    field_accuracy: null,
    documents_processed: 0,
    cost_usd: null,
    cost_per_document_usd: null,
    processing_runs: 0,
    processing_seconds_p50: null,
    processing_seconds_p95: null,
  },
  volume: {
    per_day: [],
    by_status: { NEEDS_REVIEW: 0, APPROVED: 0, FAILED: 0 },
    by_doc_type: { invoice: 0, unclassified: 0 },
  },
  llm: ["classify", "extract", "validate", "embed"].map((task) => ({ task, ...IDLE_TASK })),
  queue: {
    queued: 0,
    running: 0,
    dead: 0,
    oldest_queued_seconds: null,
    failed: 0,
    failure_reasons: [],
  },
};

const BUSY: WorkspaceMetrics = {
  ...EMPTY,
  period: "7d",
  headline: {
    ...EMPTY.headline,
    approved: 4,
    approved_without_edits: 3,
    approved_by_agent: 1,
    approved_without_edits_rate: 0.75,
    fields_reviewed: 50,
    fields_unchanged: 48,
    field_accuracy: 0.96,
    documents_processed: 5,
    cost_usd: 0.0123,
    cost_per_document_usd: 0.00246,
    processing_runs: 5,
    processing_seconds_p50: 12.4,
    processing_seconds_p95: 95,
  },
  volume: {
    per_day: [
      { date: "2026-01-08", uploaded: 1 },
      { date: "2026-01-09", uploaded: 0 },
      { date: "2026-01-10", uploaded: 4 },
    ],
    by_status: { NEEDS_REVIEW: 1, APPROVED: 4, FAILED: 0 },
    by_doc_type: { invoice: 4, unclassified: 1 },
  },
  llm: [
    { task: "classify", ...IDLE_TASK },
    {
      task: "extract",
      calls: 6,
      outcomes: { ...OUTCOMES, ok: 4, cache_hit: 1, error: 1 },
      fallback_rate: 0.2,
      served_by: [
        { provider: "gemini", model: "gemini-2.5-flash", calls: 4 },
        { provider: "groq", model: "llama", calls: 1 },
      ],
      latency_ms_p50: 2300,
    },
  ],
  queue: {
    ...EMPTY.queue,
    queued: 2,
    oldest_queued_seconds: 300,
    failed: 1,
    failure_reasons: [{ reason: "No AI key", documents: 1 }],
  },
};

function renderMetrics() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MetricsView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("token") },
    error: null,
  });
});

describe("MetricsView", () => {
  it("AC1: headline tiles, with the cost labelled as an estimate", async () => {
    routeFetch({ "/v1/me": () => Response.json(ME), "/metrics": () => Response.json(BUSY) });

    renderMetrics();

    const tile = async (label: string) =>
      (await screen.findByText(label)).parentElement as HTMLElement;
    expect(within(await tile("Approved without edits")).getByText("75%")).toBeInTheDocument();
    expect(within(await tile("Field accuracy")).getByText("96%")).toBeInTheDocument();
    const cost = await tile("Cost per document");
    expect(within(cost).getByText("$0.0025")).toBeInTheDocument();
    expect(
      within(cost).getByText(/estimated at list prices; your provider bills you/),
    ).toBeInTheDocument();
    expect(within(await tile("Processing time")).getByText("12 s")).toBeInTheDocument();
  });

  it("AC2-AC4: volume bars, AI provider table and queue", async () => {
    routeFetch({ "/v1/me": () => Response.json(ME), "/metrics": () => Response.json(BUSY) });

    renderMetrics();

    const bars = await screen.findByTestId("volume-bars");
    expect(bars.children).toHaveLength(3);
    const table = screen.getByRole("table", { name: "Documents uploaded per day" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    const extract = screen.getByRole("row", { name: /Extract/ });
    expect(within(extract).getByText("20%")).toBeInTheDocument();
    expect(within(extract).getByText(/gemini · gemini-2.5-flash/)).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Classify/ })).not.toBeInTheDocument();
    expect(screen.getByText("No AI key")).toBeInTheDocument();
    expect(screen.getByText("5.0 min")).toBeInTheDocument();
  });

  it("asks for the chosen period", async () => {
    const fetchMock = routeFetch({
      "/v1/me": () => Response.json(ME),
      "/metrics": () => Response.json(EMPTY),
    });
    renderMetrics();
    await screen.findByText("No documents in this period.");

    await userEvent.click(screen.getByRole("tab", { name: "Last 7 days" }));

    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => (input as Request).url);
      expect(urls).toContain(`http://api.test/v1/workspaces/${WORKSPACE_ID}/metrics?period=30d`);
      expect(urls).toContain(`http://api.test/v1/workspaces/${WORKSPACE_ID}/metrics?period=7d`);
    });
  });

  it("an empty workspace shows dashes and no chart", async () => {
    routeFetch({ "/v1/me": () => Response.json(ME), "/metrics": () => Response.json(EMPTY) });

    renderMetrics();

    expect(await screen.findByText("No documents in this period.")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("No AI calls in this period.")).toBeInTheDocument();
    expect(screen.queryByTestId("volume-bars")).not.toBeInTheDocument();
  });
});

describe("formatting", () => {
  it("durations and costs", () => {
    expect([duration(4.25), duration(42), duration(150), duration(7200)]).toEqual([
      "4.3 s",
      "42 s",
      "2.5 min",
      "2.0 h",
    ]);
    expect([usd(null), usd(0), usd(1.234), usd(0.00123)]).toEqual(["—", "$0", "$1.23", "$0.0012"]);
  });
});
