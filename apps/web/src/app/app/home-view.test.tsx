import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { HomeView } from "./home-view";

const supabase = createSupabaseMock();

vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const WORKSPACE_ID = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";
const ME = {
  user: {
    id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1",
    email: "ada@example.com",
    display_name: "Ada",
  },
  memberships: [{ workspace: { id: WORKSPACE_ID, name: "Ada's workspace" }, role: "admin" }],
};

function renderHome() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <HomeView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("token") },
    error: null,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("HomeView", () => {
  it("AC10: home shows email, workspace, role", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(ME));

    renderHome();

    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Ada's workspace")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe("http://api.test/v1/me");
    expect(request.headers.get("Authorization")).toBe("Bearer token");
  });

  it("says so when the user belongs to no workspace", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ ...ME, memberships: [] }));

    renderHome();

    expect(await screen.findByText("You don't belong to a workspace yet.")).toBeInTheDocument();
  });

  it("AC20: transient errors retry up to 90s, then show Try again", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new TypeError("Failed to fetch"));

    renderHome();
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByRole("status")).toHaveTextContent("Starting up the server");

    await act(() => vi.advanceTimersByTimeAsync(80_000));
    expect(screen.getByRole("status")).toHaveTextContent("Starting up the server");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't reach the DocFlow server");
    const attempts = fetchMock.mock.calls.length;
    expect(attempts).toBeGreaterThan(5);

    // No more retries once it has given up.
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(fetchMock.mock.calls.length).toBe(attempts);
  });

  it("AC20: Try again starts over and recovers when the server is up", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("", { status: 503 }));
    renderHome();
    await act(() => vi.advanceTimersByTimeAsync(100_000));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fetchMock.mockResolvedValue(Response.json(ME));
    vi.useRealTimers();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Ada's workspace")).toBeInTheDocument();
  });

  it("does not retry an error that isn't transient", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(Response.json({ title: "Internal error", status: 500 }, { status: 500 }));

    renderHome();

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
