import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/env";

/**
 * The Supabase client for Client Components. It keeps the session in cookies so that
 * `proxy.ts` can read and refresh it, and it refreshes the access token in the background.
 * In the browser `createBrowserClient` returns one shared instance.
 */
export function getSupabaseBrowserClient() {
  return createBrowserClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  );
}
