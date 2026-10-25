import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { ExtractionView } from "./extraction-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const DOCUMENT_ID = "8a6e0804-2bd0-4672-b79d-d97027f9a0a1";
const EXTRACTION = {
  id: "e1",
  version: 1,
  source: "model",
  schema_id: "docflow/invoice/v1",
  prompt_version: "extract/v1",
  created_at: "2026-10-25T10:00:00Z",
  data: {
    invoice_number: "SYN/2026-27/0142",
    due_date: null,
    vendor: { name: "Kaveri Fasteners", gstin: "29ABCDE1234F1Z5", address: null },
    line_items: [
      { description: "Steel brackets", quantity: 40, amount: { amount: 5000, currency: "INR" } },
      { description: "Hex bolts", quantity: 12, amount: { amount: 5760, currency: "INR" } },
    ],
    taxes: [],
    total: { amount: 16826.8, currency: "INR" },
  },
  confidence: {
    invoice_number: 0.99,
    "vendor.gstin": 0.55,
    "line_items.1.amount.amount": 0.4,
    "total.amount": 0.97,
  },
};

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function renderView() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExtractionView workspaceId={WORKSPACE_ID} documentId={DOCUMENT_ID} />
    </QueryClientProvider>,
  );
}

describe("ExtractionView", () => {
  it("AC6: shows fields, line items and highlights low confidence", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(EXTRACTION));

    renderView();

    expect(await screen.findByText("SYN/2026-27/0142")).toBeInTheDocument();
    expect(screen.getByText("Vendor › GSTIN")).toBeInTheDocument();
    expect(screen.getByText(/2 fields to check/)).toBeInTheDocument();

    const gstin = document.querySelector('[data-path="vendor.gstin"]') as HTMLElement;
    expect(gstin).toHaveTextContent("29ABCDE1234F1Z5");
    expect(gstin).toHaveTextContent("55%");
    expect(gstin.className).toContain("bg-amber-100");
    const number = document.querySelector('[data-path="invoice_number"]') as HTMLElement;
    expect(number.className).not.toContain("bg-amber-100");
    // Missing values show a dash, not "null".
    expect(document.querySelector('[data-path="due_date"]')).toHaveTextContent("—");

    const table = screen.getByRole("table");
    expect(within(table).getByText("Hex bolts")).toBeInTheDocument();
    const lowCell = document.querySelector(
      '[data-path="line_items.1.amount.amount"]',
    ) as HTMLElement;
    expect(lowCell).toHaveTextContent("5760");
    expect(lowCell.className).toContain("bg-amber-100");
    expect(screen.getByText("None")).toBeInTheDocument(); // empty taxes
  });

  it("AC6: raw JSON toggle", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(EXTRACTION));

    renderView();
    await userEvent.click(await screen.findByRole("tab", { name: "Raw JSON" }));

    const raw = await screen.findByText(/"invoice_number": "SYN\/2026-27\/0142"/);
    expect(raw.tagName).toBe("PRE");
    expect(raw).toHaveTextContent('"vendor.gstin": 0.55');
  });
});
