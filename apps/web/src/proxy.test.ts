// @vitest-environment node
import type { createServerClient } from "@supabase/ssr";
import { NextRequest } from "next/server";

import { config, proxy } from "./proxy";

type ServerClientOptions = Parameters<typeof createServerClient>[2];
type CookieToSet = { name: string; value: string; options: Record<string, unknown> };

// What the mocked Supabase client does when the proxy calls getClaims().
const auth = vi.hoisted(() => ({
  claims: null as Record<string, unknown> | null,
  error: null as Error | null,
  cookiesToSet: [] as CookieToSet[],
  headers: {} as Record<string, string>,
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn((_url: string, _key: string, options: ServerClientOptions) => ({
    auth: {
      getClaims: async () => {
        if (auth.cookiesToSet.length > 0 && "setAll" in options.cookies) {
          await options.cookies.setAll?.(auth.cookiesToSet, auth.headers);
        }
        return {
          data: auth.claims === null ? null : { claims: auth.claims },
          error: auth.error,
        };
      },
    },
  })),
}));

const SIGNED_IN = { sub: "user-1", role: "authenticated" };
const CACHE_HEADERS = { "Cache-Control": "private, no-cache, no-store", Expires: "0" };

function request(path: string) {
  return new NextRequest(new URL(path, "http://localhost:3000"));
}

beforeEach(() => {
  auth.claims = null;
  auth.error = null;
  auth.cookiesToSet = [];
  auth.headers = {};
});

describe("proxy", () => {
  it("AC3: sends a signed-out visitor to sign-in, remembering the page they asked for", async () => {
    const response = await proxy(request("/app/documents?status=review"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?next=%2Fapp%2Fdocuments%3Fstatus%3Dreview",
    );
  });

  it("AC3: sends a signed-out visitor from the app home to plain /login", async () => {
    const response = await proxy(request("/app"));

    expect(response.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("AC4: treats a session that can't be verified as signed out", async () => {
    auth.claims = SIGNED_IN;
    auth.error = new Error("invalid JWT");

    const response = await proxy(request("/app"));

    expect(response.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("lets a signed-in user through to app pages", async () => {
    auth.claims = SIGNED_IN;

    const response = await proxy(request("/app/documents"));

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("writes refreshed session cookies and no-store headers onto the response", async () => {
    auth.claims = SIGNED_IN;
    auth.cookiesToSet = [
      { name: "sb-test-auth-token", value: "refreshed", options: { path: "/" } },
    ];
    auth.headers = CACHE_HEADERS;

    const response = await proxy(request("/app"));

    expect(response.cookies.get("sb-test-auth-token")?.value).toBe("refreshed");
    expect(response.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
    expect(response.headers.get("expires")).toBe("0");
  });

  it("carries cookies cleared by a failed refresh onto the sign-in redirect", async () => {
    auth.cookiesToSet = [{ name: "sb-test-auth-token", value: "", options: { maxAge: 0 } }];
    auth.headers = CACHE_HEADERS;

    const response = await proxy(request("/app"));

    expect(response.status).toBe(307);
    expect(response.cookies.get("sb-test-auth-token")?.value).toBe("");
    expect(response.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
  });

  it("AC3: sends a signed-in user on the sign-in page to the safe next page", async () => {
    auth.claims = SIGNED_IN;

    const response = await proxy(request("/login?next=%2Fapp%2Fdocuments"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/app/documents");
  });

  it("AC3: ignores an unsafe next for a signed-in user", async () => {
    auth.claims = SIGNED_IN;

    const response = await proxy(request("/login?next=https%3A%2F%2Fevil.example"));

    expect(response.headers.get("location")).toBe("http://localhost:3000/app");
  });

  it("shows the sign-in page to a signed-out visitor", async () => {
    const response = await proxy(request("/login?next=%2Fapp"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("runs only on the app and the sign-in page", () => {
    expect(config.matcher).toEqual(["/app/:path*", "/login"]);
  });
});
