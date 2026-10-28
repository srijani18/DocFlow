import type { ErrorEvent } from "@sentry/nextjs";

import { ApiError } from "@/lib/api/transient";

import { scrubBreadcrumb, scrubEvent, sentryOptions, shouldReport } from "./observability";

// Shaped like real secrets, built so secret scanners see no secret.
const GOOGLE_KEY = "AIza" + "x".repeat(35);
const JWT = ["eyJ" + "a".repeat(12), "b".repeat(12), "c".repeat(12)].join(".");
const EMAIL = "ada@example.com";
const AMOUNT = "118000.50";

describe("scrubEvent", () => {
  it("AC7: removes keys, tokens, emails, query strings and document content", () => {
    const event = {
      type: undefined,
      message: `request with ${GOOGLE_KEY} for ${EMAIL}`,
      user: { id: "u-1", email: EMAIL },
      request: {
        url: "https://docflow.test/app/documents?q=acme+invoices",
        headers: { Authorization: `Bearer ${JWT}`, "User-Agent": "test" },
        cookies: { "sb-access-token": JWT },
      },
      extra: { data: { total_amount: AMOUNT }, input_tokens: 12 },
      exception: {
        values: [
          {
            type: "Error",
            value: `failed: ${JWT}`,
            stacktrace: { frames: [{ function: "ReviewForm", lineno: 10 }] },
          },
        ],
      },
      tags: { route: "/app/documents" },
    } as unknown as ErrorEvent;

    const scrubbed = scrubEvent(event);
    const text = JSON.stringify(scrubbed);

    for (const secret of [GOOGLE_KEY, JWT, EMAIL, AMOUNT, "acme"]) {
      expect(text).not.toContain(secret);
    }
    expect(scrubbed.user).toBeUndefined();
    expect(scrubbed.request?.url).toBe("https://docflow.test/app/documents");
    expect(scrubbed.exception?.values?.[0]?.stacktrace?.frames?.[0]?.function).toBe("ReviewForm");
    expect(scrubbed.tags).toEqual({ route: "/app/documents" });
    expect(scrubbed.extra).toEqual({ data: "[REDACTED]", input_tokens: 12 });
  });

  it("drops console breadcrumbs and strips query strings from navigations", () => {
    expect(scrubBreadcrumb({ category: "console", message: AMOUNT })).toBeNull();
    expect(
      scrubBreadcrumb({ category: "navigation", data: undefined, message: `to /app?q=${EMAIL}` }),
    ).toEqual({ category: "navigation", data: "[REDACTED]", message: "to /app?q=[REDACTED]" });
  });
});

describe("shouldReport", () => {
  it("AC2, AC3: server errors and bugs, not 4xx or a waking backend", () => {
    expect(shouldReport(new ApiError(500))).toBe(true);
    expect(shouldReport(new Error("bug"))).toBe(true);
    expect(shouldReport(new ApiError(404))).toBe(false);
    expect(shouldReport(new ApiError(409))).toBe(false);
    expect(shouldReport(new ApiError(503))).toBe(false);
    expect(shouldReport(new TypeError("Failed to fetch"))).toBe(false);
  });
});

describe("sentryOptions", () => {
  it("AC8: disabled without a DSN, errors only", () => {
    expect(sentryOptions(undefined)).toMatchObject({ enabled: false, tracesSampleRate: 0 });
    expect(sentryOptions("https://public@o0.ingest.sentry.io/0").enabled).toBe(true);
  });
});
