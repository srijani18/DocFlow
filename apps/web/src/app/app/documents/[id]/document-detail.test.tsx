import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { DocumentDetail } from "./document-detail";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));
// Live updates have their own tests; here they would consume the fetch mocks.
vi.mock("@/hooks/use-document-events", () => ({ useDocumentEvents: () => undefined }));

const DOCUMENT = makeDocument();

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderDetail() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DocumentDetail workspaceId={WORKSPACE_ID} documentId={DOCUMENT.id} />
    </QueryClientProvider>,
  );
}

describe("DocumentDetail", () => {
  it("AC9: view original opens a signed URL", async () => {
    const signed = "https://storage.test/documents-dev/x?token=view";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(DOCUMENT))
      .mockResolvedValueOnce(Response.json({ url: signed, expires_at: "2026-10-25T10:05:00Z" }));
    const open = vi.spyOn(window, "open").mockReturnValue(null);

    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "View original" }));

    expect(open).toHaveBeenCalledWith(signed, "_blank", "noopener,noreferrer");
    const request = fetchMock.mock.calls[1]?.[0] as Request;
    expect(request.method).toBe("POST");
    expect(request.url).toBe(
      `http://api.test/v1/workspaces/${WORKSPACE_ID}/documents/${DOCUMENT.id}/file-url`,
    );
  });

  it("shows not found for a missing or other-workspace document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ type: "x", title: "Not found", status: 404 }, { status: 404 }),
    );

    renderDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent("Document not found.");
  });
});

describe("DocumentDetail approval", () => {
  it("F6 AC6: shows that the agent approved the document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        makeDocument({
          status: "APPROVED",
          approved_at: "2026-10-26T10:00:00Z",
          approved_by_agent: true,
        }),
      ),
    );

    renderDetail();

    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/Approved automatically/)).toBeInTheDocument();
  });
});

describe("DocumentDetail retry", () => {
  it("AC8: retry button shown only for FAILED", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(makeDocument({ status: "NEEDS_REVIEW" })),
    );

    renderDetail();

    expect(await screen.findByText("Needs review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("AC8: retry requeues a failed document", async () => {
    const failed = makeDocument({
      status: "FAILED",
      failure_reason: "AI service unavailable after 5 attempts",
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(failed))
      .mockResolvedValueOnce(Response.json(makeDocument({ status: "UPLOADED" }), { status: 202 }));

    renderDetail();
    expect(await screen.findByText("AI service unavailable after 5 attempts")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    const request = fetchMock.mock.calls[1]?.[0] as Request;
    expect(request.url).toBe(
      `http://api.test/v1/workspaces/${WORKSPACE_ID}/documents/${failed.id}/retry`,
    );
  });
});

describe("DocumentDetail missing key", () => {
  it("links to Settings when no AI key is connected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        makeDocument({
          status: "FAILED",
          failure_reason: "No AI provider key connected",
          failure_code: "no_ai_key",
        }),
      ),
    );

    renderDetail();

    expect(await screen.findByRole("link", { name: "Connect a key in Settings" })).toHaveAttribute(
      "href",
      "/app/settings",
    );
  });
});
