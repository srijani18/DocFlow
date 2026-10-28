import createClient from "openapi-fetch";

import { env } from "@/env";
import type { paths } from "@/generated/api";
import { loginPath } from "@/lib/safe-next";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

/** Where the API client gets the Supabase access token from (plan §5). */
export type AuthSource = {
  /** The current access token, or null when signed out. */
  accessToken(): Promise<string | null>;
  /** A newly refreshed access token, or null when the session can't be refreshed. */
  refreshAccessToken(): Promise<string | null>;
  /** Called when the API still rejects the caller after one refresh. */
  onUnauthenticated(): void;
};

function withBearer(request: Request, token: string | null): Request {
  if (token === null) {
    return request;
  }
  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return new Request(request, { headers });
}

const READS = new Set(["GET", "HEAD", "OPTIONS"]);

/** A new Idempotency-Key for every write (F14 AC8). Set once, before the request is copied
 * for a retry, so the retry carries the same key and the API never acts twice. */
function withIdempotencyKey(request: Request): Request {
  if (READS.has(request.method) || request.headers.has("Idempotency-Key")) {
    return request;
  }
  const headers = new Headers(request.headers);
  headers.set("Idempotency-Key", crypto.randomUUID());
  return new Request(request, { headers });
}

/**
 * fetch with the Bearer token added. On a 401 it refreshes the session once and retries;
 * if that doesn't help, the user is sent to sign-in (spec edge case "expired session").
 */
function authFetch(auth: AuthSource) {
  return async (original: Request): Promise<Response> => {
    const request = withIdempotencyKey(original);
    // A request body can be read only once, so keep a copy for the retry.
    const spare = request.clone();
    const token = await auth.accessToken();
    // Resolve fetch at call time so tests (and future instrumentation) can replace it.
    const response = await globalThis.fetch(withBearer(request, token));
    if (response.status !== 401) {
      return response;
    }
    // No token means the user signed out (perhaps in another tab): nothing to refresh.
    const refreshed = token === null ? null : await auth.refreshAccessToken();
    if (refreshed === null) {
      auth.onUnauthenticated();
      return response;
    }
    const retried = await globalThis.fetch(withBearer(spare, refreshed));
    if (retried.status === 401) {
      auth.onUnauthenticated();
    }
    return retried;
  };
}

export function createApiClient(auth: AuthSource) {
  return createClient<paths>({ baseUrl: env.NEXT_PUBLIC_API_BASE_URL, fetch: authFetch(auth) });
}

const supabaseAuth: AuthSource = {
  // In the browser, getSession() reads the locally stored session, which supabase-js keeps
  // fresh in the background. The API verifies the token itself, so it needn't be trusted here.
  async accessToken() {
    const { data } = await getSupabaseBrowserClient().auth.getSession();
    return data.session?.access_token ?? null;
  },
  async refreshAccessToken() {
    const { data } = await getSupabaseBrowserClient().auth.refreshSession();
    return data.session?.access_token ?? null;
  },
  onUnauthenticated() {
    window.location.assign(loginPath(window.location.pathname + window.location.search));
  },
};

/** The current Supabase access token, for requests made outside the typed client (SSE). */
export const getAccessToken = () => supabaseAuth.accessToken();

/** Typed client generated from apps/api/openapi.json (`make gen`). Use from Client Components. */
export const api = createApiClient(supabaseAuth);
