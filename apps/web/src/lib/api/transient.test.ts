import {
  ApiError,
  COLD_START_BUDGET_MS,
  coldStartDelay,
  createColdStartRetry,
  isTransient,
  problemMessage,
} from "./transient";

describe("isTransient", () => {
  it.each([
    [
      "a network TypeError (also how a waking Render service looks, with no CORS headers)",
      new TypeError("Failed to fetch"),
    ],
    ["502", new ApiError(502)],
    ["503", new ApiError(503)],
    ["504", new ApiError(504)],
  ])("treats %s as transient", (_name, error) => {
    expect(isTransient(error)).toBe(true);
  });

  it.each([
    ["400", new ApiError(400)],
    ["401", new ApiError(401)],
    ["404", new ApiError(404)],
    ["500", new ApiError(500)],
    ["a plain Error", new Error("boom")],
    ["a non-error value", "boom"],
  ])("does not treat %s as transient", (_name, error) => {
    expect(isTransient(error)).toBe(false);
  });
});

describe("coldStartDelay", () => {
  it("doubles from 1 s and caps at 10 s", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(coldStartDelay)).toEqual([
      1000, 2000, 4000, 8000, 10_000, 10_000, 10_000,
    ]);
  });
});

describe("createColdStartRetry", () => {
  it("AC20: transient errors retry up to 90s, then stop", () => {
    let now = 0;
    const policy = createColdStartRetry(() => now);

    let failures = 0;
    while (policy.retry(failures, new TypeError("Failed to fetch"))) {
      now += policy.retryDelay(failures) + 500; // the wait, plus a failed request
      failures += 1;
    }

    expect(now).toBeLessThanOrEqual(COLD_START_BUDGET_MS + 10_500);
    expect(now).toBeGreaterThan(COLD_START_BUDGET_MS - 10_500);
    expect(failures).toBeGreaterThan(5);
  });

  it("never retries an error that isn't transient", () => {
    const policy = createColdStartRetry(() => 0);

    expect(policy.retry(0, new ApiError(500))).toBe(false);
  });

  it("starts a fresh 90 s budget for each new fetch", () => {
    let now = 0;
    const policy = createColdStartRetry(() => now);
    policy.retry(0, new TypeError("Failed to fetch"));
    now = COLD_START_BUDGET_MS + 1;
    expect(policy.retry(7, new TypeError("Failed to fetch"))).toBe(false);

    // "Try again" starts a new fetch, whose first failure has failureCount 0.
    expect(policy.retry(0, new TypeError("Failed to fetch"))).toBe(true);
  });
});

describe("ApiError", () => {
  it("keeps the status and problem details", () => {
    const error = new ApiError(503, {
      type: "x",
      title: "Service unavailable",
      status: 503,
      detail: null,
      errors: null,
      request_id: null,
    });

    expect(error.status).toBe(503);
    expect(error.problem?.title).toBe("Service unavailable");
    expect(error.message).toBe("API request failed with 503: Service unavailable");
  });
});

describe("problemMessage", () => {
  it("F14 AC10: a rate limit says how long to wait", () => {
    const limited = new ApiError(429, {
      type: "https://docflow.dev/problems/rate-limited",
      title: "Too many requests",
      status: 429,
      detail: "Too many requests. Try again in 15 s.",
      errors: null,
      request_id: null,
    });

    expect(problemMessage(limited, "x")).toBe("Too many requests. Try again in 15 s.");
    expect(problemMessage(new ApiError(429), "x")).toBe(
      "Too many requests. Try again in a minute.",
    );
    expect(problemMessage(new ApiError(500), "fallback")).toBe("fallback");
    expect(problemMessage(new TypeError("offline"), "fallback")).toBe("fallback");
  });
});
