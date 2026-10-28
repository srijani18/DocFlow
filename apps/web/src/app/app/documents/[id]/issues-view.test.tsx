import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";

import { WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { IssuesView } from "./issues-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const DOCUMENT_ID = "8a6e0804-2bd0-4672-b79d-d97027f9a0a1";

function issue(id: string, overrides: Record<string, unknown>) {
  return {
    id,
    check_name: "totals",
    severity: "error",
    paths: ["total.amount"],
    message: "Subtotal plus taxes isn't the total.",
    fixed_by_agent: false,
    created_at: "2026-10-26T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderIssues() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <IssuesView workspaceId={WORKSPACE_ID} documentId={DOCUMENT_ID} />
    </QueryClientProvider>,
  );
}

describe("IssuesView", () => {
  it("F6 AC2: lists open issues by severity, then what the agent fixed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        items: [
          issue("1", {
            check_name: "gstin",
            paths: ["vendor.gstin"],
            fixed_by_agent: true,
            message: "The vendor GSTIN checksum is wrong.",
          }),
          issue("2", {
            check_name: "known_vendor",
            severity: "info",
            paths: ["vendor"],
            message: "First document from this vendor in the workspace.",
          }),
          issue("3", {
            check_name: "duplicate",
            severity: "warning",
            paths: ["invoice_number"],
            message: "Possible duplicate.",
          }),
          issue("4", {}),
        ],
      }),
    );

    renderIssues();

    const rows = within(await screen.findByRole("list")).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringMatching(/^error.*isn't the total.*total\.amount$/),
      expect.stringMatching(/^warning.*Possible duplicate/),
      expect.stringMatching(/^info.*First document/),
      expect.stringMatching(/^Fixed by agent.*checksum is wrong.*vendor\.gstin$/),
    ]);
  });

  it("says so when every check passed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ items: [] }));

    renderIssues();

    expect(await screen.findByText("Every check passed.")).toBeInTheDocument();
  });
});
