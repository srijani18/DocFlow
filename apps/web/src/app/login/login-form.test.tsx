import {
  AuthApiError,
  AuthRetryableFetchError,
  AuthWeakPasswordError,
} from "@supabase/supabase-js";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createRouterMock } from "@/test/navigation-mock";
import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { LoginForm } from "./login-form";

const supabase = createSupabaseMock();
const router = createRouterMock();
let searchParams = new URLSearchParams();

vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

const GENERIC_SIGN_IN_ERROR = "Incorrect email or password.";

beforeEach(() => {
  searchParams = new URLSearchParams();
});

async function submit(tab: "Sign in" | "Create account", email: string, password: string) {
  const user = userEvent.setup();
  render(<LoginForm />);
  if (tab === "Create account") {
    await user.click(screen.getByRole("tab", { name: "Create account" }));
  }
  const panel = screen.getByRole("tabpanel");
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: tab }));
  return panel;
}

describe("LoginForm", () => {
  it.each([
    ["invalid_credentials", "Invalid login credentials"],
    ["email_not_confirmed", "Email not confirmed"],
    ["user_banned", "User is banned"],
  ])("AC2: invalid credentials show a generic error (%s)", async (code, message) => {
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthApiError(message, 400, code),
    });

    await submit("Sign in", "someone@example.com", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent(GENERIC_SIGN_IN_ERROR);
    expect(screen.queryByText(message)).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("AC2: valid credentials go to the page the user asked for", async () => {
    searchParams = new URLSearchParams({ next: "/app/documents" });
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { session: sessionWithToken("token") },
      error: null,
    });

    await submit("Sign in", " someone@example.com ", "correct-password");

    expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith({
      email: "someone@example.com",
      password: "correct-password",
    });
    expect(router.replace).toHaveBeenCalledWith("/app/documents");
  });

  it("AC3: an unsafe next is ignored after sign-in", async () => {
    searchParams = new URLSearchParams({ next: "https://evil.example" });
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { session: sessionWithToken("token") },
      error: null,
    });

    await submit("Sign in", "someone@example.com", "correct-password");

    expect(router.replace).toHaveBeenCalledWith("/app");
  });

  it("AC1: sign-up with valid details signs the user in and opens the app home", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { session: sessionWithToken("token") },
      error: null,
    });

    await submit("Create account", "new@example.com", "a-long-password");

    expect(supabase.auth.signUp).toHaveBeenCalledWith({
      email: "new@example.com",
      password: "a-long-password",
    });
    expect(router.replace).toHaveBeenCalledWith("/app");
  });

  it("sign-up that fails for any account reason shows a generic error", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthApiError("User already registered", 422, "user_already_exists"),
    });

    await submit("Create account", "taken@example.com", "a-long-password");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't create an account with those details.");
    expect(alert).not.toHaveTextContent("registered");
  });

  it("sign-up with a weak password explains the requirement", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthWeakPasswordError("Password should be at least 10 characters.", 422, [
        "length",
      ]),
    });

    await submit("Create account", "new@example.com", "short-pw");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password should be at least 10 characters.",
    );
  });

  it("sign-up without an immediate session asks the user to sign in", async () => {
    supabase.auth.signUp.mockResolvedValue({ data: { user: {}, session: null }, error: null });

    await submit("Create account", "new@example.com", "a-long-password");

    expect(await screen.findByRole("status")).toHaveTextContent("Account created. Sign in");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("a network failure says the sign-in service is unreachable", async () => {
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthRetryableFetchError("Failed to fetch", 0),
    });

    await submit("Sign in", "someone@example.com", "correct-password");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't reach the sign-in service",
    );
  });

  it("too many attempts asks the user to wait", async () => {
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthApiError("Request rate limit reached", 429, "over_request_rate_limit"),
    });

    await submit("Sign in", "someone@example.com", "correct-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});
