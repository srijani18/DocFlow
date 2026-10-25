import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { DocumentList } from "./documents-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

describe("live status", () => {
  it("AC9: list updates when a status event arrives", async () => {
    const document = makeDocument({ filename: "invoice.pdf" });
    let status: "EXTRACTING" | "NEEDS_REVIEW" = "EXTRACTING";
    let releaseEvent: () => void = () => undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/events")) {
        const encoder = new TextEncoder();
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode("event: ready\ndata: {}\n\n"));
            releaseEvent = () => {
              status = "NEEDS_REVIEW";
              const data = {
                document_id: document.id,
                status,
                failure_reason: null,
                changed_at: "x",
              };
              controller.enqueue(
                encoder.encode(`event: document.status\ndata: ${JSON.stringify(data)}\n\n`),
              );
            };
          },
        });
        return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
      }
      return Response.json({ items: [makeDocument({ ...document, status })], next_cursor: null });
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <DocumentList workspaceId={WORKSPACE_ID} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Extracting")).toBeInTheDocument();
    releaseEvent();
    expect(await screen.findByText("Needs review")).toBeInTheDocument();
  });
});
