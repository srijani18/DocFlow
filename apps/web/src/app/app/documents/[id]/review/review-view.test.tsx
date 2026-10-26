import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeDocument, WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { Review } from "./review-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const DOCUMENT = makeDocument({
  status: "NEEDS_REVIEW",
  doc_type: "invoice",
  content_type: "application/pdf",
});
const SCHEMA = {
  type: "object",
  properties: {
    invoice_number: { type: ["string", "null"] },
    invoice_date: { type: ["string", "null"], format: "date" },
    total: {
      anyOf: [
        {
          type: "object",
          properties: {
            amount: { type: ["number", "null"] },
            currency: { type: ["string", "null"] },
          },
        },
        { type: "null" },
      ],
    },
  },
};
const EXTRACTION = {
  id: "e1",
  version: 1,
  source: "model",
  schema_id: "docflow/invoice/v1",
  prompt_version: "extract/v1",
  created_at: "2026-10-26T10:00:00Z",
  data: {
    invoice_number: "INV-1",
    invoice_date: "2026-08-14",
    total: { amount: 18826.8, currency: "INR" },
  },
  confidence: { invoice_number: 0.99, invoice_date: 0.6, "total.amount": 0.95 },
};
const ISSUES = {
  items: [
    {
      id: "i1",
      check_name: "totals",
      severity: "error",
      paths: ["total.amount"],
      message: "Subtotal plus taxes is 16826.80, but the total is 18826.80.",
      fixed_by_agent: false,
      created_at: "2026-10-26T10:00:00Z",
    },
  ],
};

type Handler = (request: Request) => Response | Promise<Response>;

function serve(overrides: Record<string, Handler> = {}) {
  const requests: Request[] = [];
  const routes: Record<string, Handler> = {
    [`/documents/${DOCUMENT.id}`]: () => Response.json(DOCUMENT),
    "/extraction": () => Response.json(EXTRACTION),
    "/issues": () => Response.json(ISSUES),
    "/file-url": () =>
      Response.json({ url: "https://storage.test/x.pdf", expires_at: "2026-10-26T10:05:00Z" }),
    v1: () => Response.json(SCHEMA), // the schema id is the last path segment
    ...overrides,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input instanceof Request ? input : new Request(String(input));
    requests.push(request.clone());
    const path = new URL(request.url).pathname;
    const key = Object.keys(routes).find((suffix) => path.endsWith(suffix));
    return key ? routes[key]!(request) : new Response("not mocked", { status: 599 });
  });
  return requests;
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderReview() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Review workspaceId={WORKSPACE_ID} documentId={DOCUMENT.id} />
    </QueryClientProvider>,
  );
}

describe("Review", () => {
  it("AC1, AC2: original beside the form, with problems listed and Next problem", async () => {
    serve();

    renderReview();

    expect(await screen.findByTitle(`Original: ${DOCUMENT.filename}`)).toHaveAttribute(
      "src",
      "https://storage.test/x.pdf",
    );
    expect(screen.getByLabelText("Invoice number")).toHaveValue("INV-1");
    expect(screen.getByText("2 things to check")).toBeInTheDocument();
    expect(screen.getByText(/invoice_date is only 60% certain/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next problem" }));
    expect(screen.getByLabelText("Invoice date")).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Next problem" }));
    expect(screen.getByLabelText("Total › Amount")).toHaveFocus();
  });

  it("AC3: an invalid value shows a message and blocks saving", async () => {
    serve();
    renderReview();
    const date = await screen.findByLabelText("Invoice date");

    await userEvent.clear(date);
    await userEvent.type(date, "14-08-2026");

    expect(screen.getByText("Enter a date as YYYY-MM-DD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
  });

  it("AC4: save sends the base version and the whole corrected data", async () => {
    const requests = serve({
      "/extraction": (request) =>
        request.method === "PUT"
          ? Response.json({ ...EXTRACTION, version: 2, source: "human" })
          : Response.json(EXTRACTION),
    });
    renderReview();
    const amount = await screen.findByLabelText("Total › Amount");

    await userEvent.clear(amount);
    await userEvent.type(amount, "16826.80");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(requests.some((r) => r.method === "PUT")).toBe(true));
    const put = requests.find((r) => r.method === "PUT")!;
    expect(await put.json()).toEqual({
      base_version: 1,
      data: { ...EXTRACTION.data, total: { amount: 16826.8, currency: "INR" } },
    });
  });

  it("AC5: errors need Approve anyway", async () => {
    const approvals: unknown[] = [];
    serve({
      "/approve": async (request) => {
        const body = (await request.json()) as { accept_errors: boolean };
        approvals.push(body);
        return body.accept_errors
          ? Response.json({ ...DOCUMENT, status: "APPROVED" })
          : Response.json(
              {
                type: "https://docflow.dev/problems/open-errors",
                title: "This document has unresolved errors",
                status: 409,
                detail: ISSUES.items[0]!.message,
              },
              { status: 409 },
            );
      },
    });
    renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve anyway" }));

    await waitFor(() => expect(approvals).toHaveLength(2));
    expect(approvals).toEqual([
      { version: 1, data: null, accept_errors: false },
      { version: 1, data: null, accept_errors: true },
    ]);
  });

  it("AC6: a stale version shows the conflict message", async () => {
    serve({
      "/approve": () =>
        Response.json(
          {
            type: "https://docflow.dev/problems/version-conflict",
            title: "This document changed since you opened it",
            status: 409,
          },
          { status: 409 },
        ),
    });
    renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This document changed since you opened it",
    );
    expect(screen.getByRole("button", { name: "Reload document" })).toBeInTheDocument();
  });

  it("approved documents are read-only", async () => {
    serve({
      [`/documents/${DOCUMENT.id}`]: () => Response.json({ ...DOCUMENT, status: "APPROVED" }),
    });
    renderReview();

    expect(await screen.findByLabelText("Invoice number")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
