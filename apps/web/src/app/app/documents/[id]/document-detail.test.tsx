import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { DocumentDetail } from "./document-detail";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

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
