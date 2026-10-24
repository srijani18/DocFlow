import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/proxy";
import { loginPath, safeNext } from "@/lib/safe-next";

/**
 * Runs before app pages and the sign-in page render (Next 16's replacement for middleware).
 * It keeps the Supabase session fresh, sends signed-out visitors to sign-in (spec AC3, AC4)
 * and sends signed-in visitors away from it. The API checks every request's token itself,
 * so this is a convenience for the UI, not the security boundary.
 */
export async function proxy(request: NextRequest) {
  const session = await updateSession(request);
  const { pathname, search } = request.nextUrl;

  if (pathname === "/login") {
    if (!session.signedIn) {
      return session.response;
    }
    const next = safeNext(request.nextUrl.searchParams.get("next"));
    return session.carryOver(NextResponse.redirect(new URL(next, request.url)));
  }

  if (!session.signedIn) {
    return session.carryOver(
      NextResponse.redirect(new URL(loginPath(pathname + search), request.url)),
    );
  }
  return session.response;
}

export const config = {
  matcher: ["/app/:path*", "/login"],
};
