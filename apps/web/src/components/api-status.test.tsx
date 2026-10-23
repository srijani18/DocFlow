import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { ApiStatus } from "./api-status";

function renderWithQueryClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApiStatus />
    </QueryClientProvider>,
  );
}

describe("ApiStatus", () => {
  it("landing shows API status ok", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(Response.json({ status: "ok" }));

    renderWithQueryClient();

    expect(await screen.findByText("API: ok")).toBeInTheDocument();
    const request = fetchMock.mock.calls[0]?.[0];
    expect(request).toBeInstanceOf(Request);
    expect((request as Request).url).toBe("http://api.test/healthz");
  });

  it("landing shows API status unavailable when the request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    renderWithQueryClient();

    expect(await screen.findByText("API: unavailable")).toBeInTheDocument();
  });

  it("landing shows API status unavailable on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 502 }));

    renderWithQueryClient();

    expect(await screen.findByText("API: unavailable")).toBeInTheDocument();
  });
});
