import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { Documents } from "./documents-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));
vi.mock("@/hooks/use-document-events", () => ({ useDocumentEvents: () => undefined }));

const KAVERI = makeDocument({
  id: "k1",
  filename: "kaveri.pdf",
  status: "NEEDS_REVIEW",
  doc_type: "invoice",
  vendor_name: "Kaveri Fasteners Private Limited",
});

function serve(results: { semantic: boolean }) {
  const urls: URL[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input instanceof Request ? input : new Request(String(input));
    const url = new URL(request.url);
    urls.push(url);
    if (url.pathname.endsWith("/search")) {
      return Response.json({
        items: [{ document: KAVERI, matched: "both", snippet: "[[Kaveri]] Fasteners Private" }],
        next_cursor: null,
        semantic: results.semantic,
      });
    }
    return Response.json({ items: [], next_cursor: null });
  });
  return urls;
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderDocuments() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Documents workspaceId={WORKSPACE_ID} />
    </QueryClientProvider>,
  );
}

describe("Search", () => {
  it("F8 AC1: typing searches, and results show why they matched", async () => {
    const urls = serve({ semantic: true });
    renderDocuments();

    await userEvent.type(screen.getByLabelText("Search documents"), "kaveri");

    const row = (await screen.findByRole("link", { name: "kaveri.pdf" })).closest("tr")!;
    expect(within(row).getByText("Keyword + meaning")).toBeInTheDocument();
    expect(within(row).getByText("Kaveri", { selector: "mark" })).toBeInTheDocument();
    const search = urls.filter((url) => url.pathname.endsWith("/search"));
    expect(search.at(-1)!.searchParams.get("q")).toBe("kaveri");
    expect(screen.queryByText(/keyword matches only/)).not.toBeInTheDocument();
  });

  it("F8 AC4: filters go to the API", async () => {
    const urls = serve({ semantic: true });
    renderDocuments();

    await userEvent.click(screen.getByRole("button", { name: /Filters/ }));
    await userEvent.selectOptions(screen.getByLabelText("Status"), "APPROVED");
    await userEvent.type(screen.getByLabelText("Vendor"), "kav");

    await screen.findByRole("link", { name: "kaveri.pdf" });
    const last = urls.filter((url) => url.pathname.endsWith("/search")).at(-1)!;
    expect(Object.fromEntries(last.searchParams)).toEqual({ status: "APPROVED", vendor: "kav" });
    expect(screen.getByRole("button", { name: "Filters (2)" })).toBeInTheDocument();
  });

  it("F8 AC5: says when only keyword matches are shown", async () => {
    serve({ semantic: false });
    renderDocuments();

    await userEvent.type(screen.getByLabelText("Search documents"), "supplier");

    expect(await screen.findByText(/Showing keyword matches only/)).toBeInTheDocument();
  });
});
