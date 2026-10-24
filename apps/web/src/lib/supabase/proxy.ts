import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/env";

export type SessionResult = {
  /** Pass-through response carrying any refreshed session cookies. */
  response: NextResponse;
  signedIn: boolean;
  /** Copies the session cookies and no-store headers onto another response, e.g. a redirect. */
  carryOver: (target: NextResponse) => NextResponse;
};

/**
 * Verifies and, when needed, refreshes the Supabase session for one request, following
 * Supabase's Next.js guide. Only the proxy refreshes on the server: Server Components never
 * touch the session, so a refresh token is never used twice by the server.
 */
export async function updateSession(request: NextRequest): Promise<SessionResult> {
  let response = NextResponse.next({ request });
  // Auth cookies must never be cached by a CDN, or one user's session could reach another.
  const noStoreHeaders: Record<string, string> = {};

  // A new client per request: the cookie callbacks are bound to this request and response.
  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          // Update the request too, so pages rendered for this request see the new session.
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
          Object.assign(noStoreHeaders, headers);
          for (const [key, value] of Object.entries(headers)) {
            response.headers.set(key, value);
          }
        },
      },
    },
  );

  // Nothing may run between creating the client and getClaims(). getClaims() verifies the
  // access token's signature (cookies can be forged) and refreshes it when it has expired.
  const { data, error } = await supabase.auth.getClaims();
  const signedIn = error === null && data !== null;

  return {
    response,
    signedIn,
    carryOver(target) {
      for (const cookie of response.cookies.getAll()) {
        target.cookies.set(cookie);
      }
      for (const [key, value] of Object.entries(noStoreHeaders)) {
        target.headers.set(key, value);
      }
      return target;
    },
  };
}
