import type { MockInstance } from "vitest";

import { createApiClient, type AuthSource } from "./client";

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: () => {
    throw new Error("tests pass their own AuthSource");
  },
}));

function fakeAuth(tokens: { current: string | null; refreshed: string | null }) {
  return {
    accessToken: vi.fn(async () => tokens.current),
    refreshAccessToken: vi.fn(async () => tokens.refreshed),
    onUnauthenticated: vi.fn(),
  } satisfies AuthSource;
}

const ME = {
  user: { id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1", email: "a@example.com", display_name: null },
  memberships: [],
};
const UNAUTHENTICATED = new Response(
  JSON.stringify({ type: "about:blank", title: "Unauthenticated", status: 401 }),
  { status: 401, headers: { "Content-Type": "application/problem+json" } },
);

function sentRequests(fetchMock: MockInstance<typeof fetch>) {
  return fetchMock.mock.calls.map(([input]) => input as Request);
}

describe("API client auth", () => {
  it("client adds the Bearer token and refreshes once on 401", async () => {
    const auth = fakeAuth({ current: "expired-token", refreshed: "fresh-token" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(UNAUTHENTICATED.clone())
      .mockResolvedValueOnce(Response.json(ME));

    const { data } = await createApiClient(auth).GET("/v1/me");

    expect(data).toEqual(ME);
    const [first, retry] = sentRequests(fetchMock);
    expect(first?.headers.get("Authorization")).toBe("Bearer expired-token");
    expect(retry?.headers.get("Authorization")).toBe("Bearer fresh-token");
    expect(retry?.url).toBe("http://api.test/v1/me");
    expect(auth.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(auth.onUnauthenticated).not.toHaveBeenCalled();
  });

  it("resends the request body on the retry", async () => {
    const auth = fakeAuth({ current: "expired-token", refreshed: "fresh-token" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(UNAUTHENTICATED.clone())
      .mockResolvedValueOnce(Response.json({}));
    const workspaceId = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";

    await createApiClient(auth).PATCH("/v1/workspaces/{workspace_id}", {
      params: { path: { workspace_id: workspaceId } },
      body: { name: "Renamed" },
    });

    const retry = sentRequests(fetchMock)[1];
    expect(retry?.method).toBe("PATCH");
    expect(await retry?.json()).toEqual({ name: "Renamed" });
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(Response.json({ status: "ok" }));

    await createApiClient(fakeAuth({ current: null, refreshed: null })).GET("/healthz");

    expect(sentRequests(fetchMock)[0]?.headers.has("Authorization")).toBe(false);
  });

  it("sends the user to sign-in when the session can't be refreshed", async () => {
    const auth = fakeAuth({ current: "expired-token", refreshed: null });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(UNAUTHENTICATED.clone());

    const { error, response } = await createApiClient(auth).GET("/v1/me");

    expect(response.status).toBe(401);
    expect(error).toMatchObject({ title: "Unauthenticated" });
    expect(auth.onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it("refreshes only once: a second 401 sends the user to sign-in", async () => {
    const auth = fakeAuth({ current: "expired-token", refreshed: "also-rejected" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => UNAUTHENTICATED.clone());

    await createApiClient(auth).GET("/v1/me");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(auth.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(auth.onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it("does not try to refresh when there was no session (signed out in another tab)", async () => {
    const auth = fakeAuth({ current: null, refreshed: "unused" });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(UNAUTHENTICATED.clone());

    await createApiClient(auth).GET("/v1/me");

    expect(auth.refreshAccessToken).not.toHaveBeenCalled();
    expect(auth.onUnauthenticated).toHaveBeenCalledTimes(1);
  });
});
