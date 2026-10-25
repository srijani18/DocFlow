import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * A stand-in for the browser Supabase client with only the auth methods the app uses.
 * Tests mock `@/lib/supabase/browser` to return it.
 */
export function createSupabaseMock() {
  const auth = {
    signInWithPassword: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn().mockResolvedValue({ error: null }),
    getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    refreshSession: vi.fn(),
  };
  const uploadToSignedUrl = vi.fn().mockResolvedValue({ data: { path: "p" }, error: null });
  const storage = { from: vi.fn(() => ({ uploadToSignedUrl })) };
  return {
    auth,
    storage,
    uploadToSignedUrl,
    client: { auth, storage } as unknown as SupabaseClient,
  };
}

export function sessionWithToken(accessToken: string) {
  return { access_token: accessToken, refresh_token: "refresh", token_type: "bearer" };
}
