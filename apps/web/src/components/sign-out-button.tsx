"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

/**
 * Ends the session in this browser (spec AC4). "local" scope leaves the user's other
 * devices signed in. supabase-js removes the session cookies even when the call to
 * Supabase fails, so sign-out always works offline too.
 */
export function SignOutButton() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function signOut() {
    setPending(true);
    await getSupabaseBrowserClient().auth.signOut({ scope: "local" });
    // Drop cached API data so the next person using this browser can't see it.
    queryClient.clear();
    router.replace("/login");
    // Discard pages cached by the client-side router, so Back can't show the app.
    router.refresh();
  }

  return (
    <Button variant="outline" onClick={signOut} disabled={pending}>
      Sign out
    </Button>
  );
}
