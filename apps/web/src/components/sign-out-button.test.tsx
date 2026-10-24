import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createRouterMock } from "@/test/navigation-mock";
import { createSupabaseMock } from "@/test/supabase-mock";

import { SignOutButton } from "./sign-out-button";

const supabase = createSupabaseMock();
const router = createRouterMock();

vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

function renderButton() {
  const queryClient = new QueryClient();
  queryClient.setQueryData(["me"], { user: { email: "someone@example.com" } });
  render(
    <QueryClientProvider client={queryClient}>
      <SignOutButton />
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("SignOutButton", () => {
  it("AC4: sign-out clears the session and redirects", async () => {
    const queryClient = renderButton();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(queryClient.getQueryData(["me"])).toBeUndefined();
    expect(router.replace).toHaveBeenCalledWith("/login");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("AC4: still clears local data and redirects when Supabase can't be reached", async () => {
    supabase.auth.signOut.mockResolvedValueOnce({ error: new Error("Failed to fetch") });
    const queryClient = renderButton();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(queryClient.getQueryData(["me"])).toBeUndefined();
    expect(router.replace).toHaveBeenCalledWith("/login");
  });
});
