import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { routeFetch } from "@/test/fetch-router";
import { WORKSPACE_ID } from "@/test/fixtures";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { AiKeys } from "./ai-keys-view";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

function status(provider: string, connected = false, extra: Record<string, unknown> = {}) {
  return {
    provider,
    connected,
    last4: connected ? "9f3k" : null,
    status: connected ? "ok" : null,
    checked_at: connected ? "2026-10-26T10:00:00Z" : null,
    updated_at: connected ? "2026-10-26T10:00:00Z" : null,
    ...extra,
  };
}

function renderKeys(isAdmin = true) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AiKeys workspaceId={WORKSPACE_ID} isAdmin={isAdmin} />
    </QueryClientProvider>,
  );
}

describe("AI keys settings", () => {
  it("AC1: admin saves a key; only the last 4 characters are shown afterwards", async () => {
    let saved = false;
    const fetchMock = routeFetch({
      "/ai-keys/gemini": () => {
        saved = true;
        return Response.json(status("gemini", true));
      },
      "/ai-keys": () =>
        Response.json([status("gemini", saved), status("groq"), status("openrouter")]),
    });
    renderKeys();

    const card = await screen.findByRole("region", { name: "Google Gemini" });
    expect(within(card).getByText("Not connected")).toBeInTheDocument();
    await userEvent.type(
      within(card).getByLabelText("Google Gemini API key"),
      "fake-test-key-9f3k",
    );
    await userEvent.click(within(card).getByRole("button", { name: "Save key" }));

    expect(await within(card).findByText("Connected · …9f3k")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("fake-test-key-9f3k")).not.toBeInTheDocument();
    const put = fetchMock.mock.calls.map(([r]) => r as Request).find((r) => r.method === "PUT");
    expect(await put?.json()).toEqual({ api_key: "fake-test-key-9f3k" });
  });

  it("AC1: an invalid key shows the provider's message", async () => {
    routeFetch({
      "/ai-keys/groq": () =>
        Response.json(
          {
            type: "x/invalid-api-key",
            title: "The provider didn't accept this key",
            status: 422,
            detail: "This doesn't look like a valid groq key.",
          },
          { status: 422 },
        ),
      "/ai-keys": () => Response.json([status("gemini"), status("groq"), status("openrouter")]),
    });
    renderKeys();

    const card = await screen.findByRole("region", { name: "Groq" });
    await userEvent.type(within(card).getByLabelText("Groq API key"), "gsk_wrong_key");
    await userEvent.click(within(card).getByRole("button", { name: "Save key" }));

    expect(await within(card).findByRole("alert")).toHaveTextContent(
      "This doesn't look like a valid groq key.",
    );
  });

  it("AC3: reviewers see status but no controls", async () => {
    routeFetch({
      "/ai-keys": () =>
        Response.json([status("gemini", true), status("groq"), status("openrouter")]),
    });
    renderKeys(false);

    const card = await screen.findByRole("region", { name: "Google Gemini" });
    expect(within(card).getByText("Connected · …9f3k")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/API key/)).not.toBeInTheDocument();
    expect(screen.getByText(/Only workspace admins can add or change keys/)).toBeInTheDocument();
  });

  it("AC5 and AC9: test marks a rejected key; remove disconnects", async () => {
    let state = status("gemini", true);
    routeFetch({
      "/ai-keys/gemini/test": () => {
        state = status("gemini", true, { status: "rejected" });
        return Response.json(state);
      },
      "/ai-keys/gemini": () => {
        state = status("gemini");
        return new Response(null, { status: 204 });
      },
      "/ai-keys": () => Response.json([state, status("groq"), status("openrouter")]),
    });
    renderKeys();

    const card = await screen.findByRole("region", { name: "Google Gemini" });
    await userEvent.click(within(card).getByRole("button", { name: "Test" }));
    expect(await within(card).findByText("Key rejected")).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "Remove" }));
    expect(await within(card).findByText("Not connected")).toBeInTheDocument();
  });
});
