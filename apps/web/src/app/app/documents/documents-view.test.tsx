import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { DocumentList } from "./documents-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));
// Live updates have their own tests; here they would consume the fetch mocks.
vi.mock("@/hooks/use-document-events", () => ({ useDocumentEvents: () => undefined }));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderList() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <DocumentList workspaceId={WORKSPACE_ID} />
    </QueryClientProvider>,
  );
}

describe("DocumentList", () => {
  it("AC8: list renders and loads more", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        Response.json({
          items: [
            makeDocument({
              id: "1",
              filename: "newest.pdf",
              size_bytes: 2048,
              doc_type: "invoice",
              doc_type_confidence: 0.914,
            }),
          ],
          next_cursor: "c1",
        }),
      )
      .mockResolvedValueOnce(
        Response.json({
          items: [makeDocument({ id: "2", filename: "older.png" })],
          next_cursor: null,
        }),
      );

    renderList();

    expect(await screen.findByRole("link", { name: "newest.pdf" })).toHaveAttribute(
      "href",
      "/app/documents/1",
    );
    const row = screen.getByRole("row", { name: /newest\.pdf/ });
    expect(row).toHaveTextContent("Queued");

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("link", { name: "older.png" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    const second = fetchMock.mock.calls[1]?.[0] as Request;
    expect(new URL(second.url).searchParams.get("cursor")).toBe("c1");
  });

  it("shows an empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ items: [], next_cursor: null }),
    );

    renderList();

    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  });
});

describe("DocumentList types", () => {
  it("AC1: list shows type and confidence", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        items: [
          makeDocument({
            id: "1",
            filename: "a.pdf",
            doc_type: "purchase_order",
            doc_type_confidence: 0.914,
          }),
          makeDocument({ id: "2", filename: "b.pdf", doc_type: null, doc_type_confidence: null }),
        ],
        next_cursor: null,
      }),
    );

    renderList();

    expect(await screen.findByRole("row", { name: /a\.pdf/ })).toHaveTextContent(
      "Purchase order · 91%",
    );
    expect(screen.getByRole("row", { name: /b\.pdf/ })).toHaveTextContent("—");
  });
});

describe("DocumentList summary", () => {
  it("AC7: list shows vendor and total", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        items: [
          makeDocument({
            id: "1",
            filename: "inv.pdf",
            vendor_name: "Kaveri Fasteners Private Limited",
            total_amount: "16826.80",
            currency: "INR",
          }),
        ],
        next_cursor: null,
      }),
    );

    renderList();

    const row = await screen.findByRole("row", { name: /inv\.pdf/ });
    expect(row).toHaveTextContent("Kaveri Fasteners Private Limited");
    expect(row).toHaveTextContent("₹16,826.80");
  });
});
