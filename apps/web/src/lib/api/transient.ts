/**
 * What counts as "the backend is waking up or briefly unreachable", and how long the app
 * keeps retrying (spec AC20, plan §5). Render's free tier sleeps after 15 idle minutes and
 * takes about a minute to wake.
 */

import type { components } from "@/generated/api";

export type Problem = components["schemas"]["Problem"];

/** A non-2xx API response, with its RFC 9457 problem body when there is one. */
export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly status: number,
    readonly problem?: Problem,
  ) {
    super(`API request failed with ${status}${problem ? `: ${problem.title}` : ""}`);
  }
}

function isProblem(value: unknown): value is Problem {
  return typeof value === "object" && value !== null && "title" in value && "status" in value;
}

/** An ApiError for a failed openapi-fetch call, keeping the problem body when there is one. */
export function toApiError(response: Response, error: unknown): ApiError {
  return new ApiError(response.status, isProblem(error) ? error : undefined);
}

const TRANSIENT_STATUSES = new Set([502, 503, 504]);

export const COLD_START_BUDGET_MS = 90_000;
const MAX_DELAY_MS = 10_000;

/**
 * A network-level failure (fetch rejects with TypeError) or a gateway or "unavailable"
 * status. While Render wakes a service its responses have no CORS headers, so the browser
 * reports them as a network TypeError too.
 */
export function isTransient(error: unknown): boolean {
  if (error instanceof TypeError) {
    return true;
  }
  return error instanceof ApiError && TRANSIENT_STATUSES.has(error.status);
}

/** Wait before retry number `attempt` (0-based): 1 s, 2 s, 4 s, 8 s, then 10 s. */
export function coldStartDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, MAX_DELAY_MS);
}

/**
 * TanStack Query `retry` and `retryDelay` options that retry transient errors until the
 * next attempt would start more than 90 s after the first failure. Create one per query:
 * it remembers when the current fetch first failed.
 */
export function createColdStartRetry(now: () => number = Date.now) {
  let firstFailureAt = 0;
  return {
    retry(failureCount: number, error: unknown): boolean {
      if (failureCount === 0) {
        firstFailureAt = now();
      }
      if (!isTransient(error)) {
        return false;
      }
      return now() + coldStartDelay(failureCount) - firstFailureAt <= COLD_START_BUDGET_MS;
    },
    retryDelay: coldStartDelay,
  };
}
