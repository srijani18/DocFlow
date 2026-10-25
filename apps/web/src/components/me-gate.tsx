"use client";

import type { ReactNode } from "react";

import { BackendUnavailable, BackendWaking } from "@/components/backend-waking";
import { useMe, type Me } from "@/lib/api/me";
import { isTransient } from "@/lib/api/transient";

/**
 * Renders `children` once the signed-in user is loaded. Until then it shows loading,
 * the "starting up" banner while the API wakes, or an error with Try again (F1 AC20).
 */
export function MeGate({ children }: { children: (me: Me) => ReactNode }) {
  const me = useMe();

  if (me.isSuccess) {
    return children(me.data);
  }
  if (me.isFetching && me.failureCount > 0 && isTransient(me.failureReason)) {
    return <BackendWaking />;
  }
  if (me.isError && !me.isFetching) {
    return (
      <BackendUnavailable
        reason={isTransient(me.error) ? "unreachable" : "error"}
        onRetry={() => void me.refetch()}
      />
    );
  }
  return <p className="text-sm text-muted-foreground">Loading your account…</p>;
}
