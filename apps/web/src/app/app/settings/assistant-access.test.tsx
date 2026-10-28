import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { routeFetch } from "@/test/fetch-router";
import { WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { AssistantAccess, clientSnippets } from "./assistant-access";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

const NEW_TOKEN = "dfw_" + "x".repeat(43);

function token(overrides: Record<string, unknown> = {}) {
  return {
    id: "6f0c1d2e-0000-4000-8000-000000000001",
    name: "Claude on my laptop",
    prefix: "dfw_abcd",
    created_by: "ada@example.com",
    created_at: "2026-10-28T10:00:00Z",
    expires_at: "2099-01-26T10:00:00Z",
    last_used_at: null,
    revoked_at: null,
    active: true,
    ...overrides,
  };
}

function renderAccess(isAdmin = false) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AssistantAccess workspaceId={WORKSPACE_ID} isAdmin={isAdmin} />
    </QueryClientProvider>,
  );
}

describe("AI assistant access tokens", () => {
  it("AC1: a new token is shown once, with client snippets", async () => {
    let created = false;
    const fetchMock = routeFetch({
      "/api-tokens": () => {
        // GET lists, POST creates: the router matches by path only.
        return created ? Response.json([token()]) : Response.json([]);
      },
    });
    fetchMock.mockImplementationOnce(async () => Response.json([]));
    fetchMock.mockImplementationOnce(async () => {
      created = true;
      return Response.json({ ...token(), token: NEW_TOKEN }, { status: 201 });
    });
    renderAccess();

    expect(await screen.findByText("No tokens yet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Token name"), "Claude on my laptop");
    await userEvent.selectOptions(screen.getByLabelText("Expires after"), "30");
    await userEvent.click(screen.getByRole("button", { name: "Create token" }));

    expect(await screen.findByLabelText("New token")).toHaveTextContent(NEW_TOKEN);
    expect(screen.getByText(/claude mcp add --transport http docflow/)).toBeInTheDocument();
    const post = fetchMock.mock.calls.map(([r]) => r as Request).find((r) => r.method === "POST");
    expect(await post?.json()).toEqual({ name: "Claude on my laptop", expires_in_days: 30 });

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText(NEW_TOKEN)).not.toBeInTheDocument();
    const row = await screen.findByRole("row", { name: /Claude on my laptop/ });
    expect(within(row).getByText("dfw_abcd…")).toBeInTheDocument();
  });

  it("AC3: revoking asks for confirmation", async () => {
    const fetchMock = routeFetch({
      [`/api-tokens/${token().id}`]: () => new Response(null, { status: 204 }),
      "/api-tokens": () => Response.json([token()]),
    });
    renderAccess(true);

    const row = await screen.findByRole("row", { name: /Claude on my laptop/ });
    expect(within(row).getByText("ada@example.com")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    await userEvent.click(within(row).getByRole("button", { name: "Confirm revoke" }));

    await vi.waitFor(() => {
      const methods = fetchMock.mock.calls.map(([r]) => (r as Request).method);
      expect(methods).toContain("DELETE");
    });
  });

  it("shows revoked and inactive tokens without a revoke button", async () => {
    routeFetch({
      "/api-tokens": () =>
        Response.json([
          token({ id: "a", name: "old", revoked_at: "2026-10-28T11:00:00Z", active: false }),
          token({ id: "b", name: "left", active: false }),
        ]),
    });
    renderAccess();

    const revoked = await screen.findByRole("row", { name: /old/ });
    const inactive = screen.getByRole("row", { name: /left/ });
    expect(within(revoked).getByText("Revoked")).toBeInTheDocument();
    expect(within(inactive).getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });
});

describe("clientSnippets", () => {
  it("puts the token in a header, never in the URL", () => {
    for (const snippet of clientSnippets(NEW_TOKEN)) {
      expect(snippet.text).toContain(`Bearer ${NEW_TOKEN}`);
      expect(snippet.text).toMatch(/http:\/\/api\.test\/mcp\b/);
      expect(snippet.text).not.toContain(`mcp?`);
    }
  });
});
