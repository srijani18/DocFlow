import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { attachmentName } from "@/lib/api/export";
import { EMPTY_SEARCH } from "@/lib/api/search";
import { WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { ExportMenu } from "./export-menu";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderMenu() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExportMenu workspaceId={WORKSPACE_ID} search={{ ...EMPTY_SEARCH, q: "kaveri" }} />
    </QueryClientProvider>,
  );
}

describe("ExportMenu", () => {
  it("F9: downloads with the active search and saves the file", async () => {
    const urls: URL[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(String(input));
      urls.push(new URL(request.url));
      return new Response(new Blob(["PK"]), {
        headers: {
          "content-type": "application/zip",
          "content-disposition": 'attachment; filename="docflow-export-20261027-1000.zip"',
        },
      });
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByLabelText("Include documents not yet approved"));
    await userEvent.click(screen.getByRole("button", { name: "CSV (.zip)" }));

    await vi.waitFor(() => expect(click).toHaveBeenCalled());
    expect(Object.fromEntries(urls[0]!.searchParams)).toEqual({
      q: "kaveri",
      format: "csv",
      include_unapproved: "true",
    });
  });

  it("F9 AC6: explains when there are too many documents", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        {
          type: "https://docflow.dev/problems/export-too-large",
          title: "Too many documents to export",
          status: 422,
          detail: "6,200 documents match. Narrow the filters to 5,000 or fewer.",
        },
        { status: 422 },
      ),
    );

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByRole("button", { name: "JSON" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Narrow the filters");
  });

  it("reads the file name from the response", () => {
    expect(attachmentName('attachment; filename="a.zip"', "csv")).toBe("a.zip");
    expect(attachmentName(null, "json")).toBe("docflow-export.json");
  });
});
