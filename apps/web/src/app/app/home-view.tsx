"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { BackendUnavailable, BackendWaking } from "@/components/backend-waking";
import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { ApiError, createColdStartRetry, isTransient, type Problem } from "@/lib/api/transient";

type Me = components["schemas"]["Me"];
type Role = components["schemas"]["Role"];

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", reviewer: "Reviewer" };

function isProblem(value: unknown): value is Problem {
  return typeof value === "object" && value !== null && "title" in value && "status" in value;
}

async function fetchMe(): Promise<Me> {
  const { data, error, response } = await api.GET("/v1/me");
  if (data === undefined) {
    throw new ApiError(response.status, isProblem(error) ? error : undefined);
  }
  return data;
}

/** The app home: who is signed in, their workspace and role (spec AC10). */
export function HomeView() {
  // One retry policy per mounted page: it tracks when the current fetch first failed.
  const [coldStartRetry] = useState(() => createColdStartRetry());
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, ...coldStartRetry });

  if (me.isSuccess) {
    return <Account me={me.data} />;
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

function Account({ me }: { me: Me }) {
  // F1 has one personal workspace per user; switching workspaces is a non-goal.
  const membership = me.memberships[0];
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
      <dt className="text-muted-foreground">Signed in as</dt>
      <dd>{me.user.email ?? me.user.display_name ?? "Your account"}</dd>
      {membership === undefined ? (
        <dd className="col-span-2">You don&apos;t belong to a workspace yet.</dd>
      ) : (
        <>
          <dt className="text-muted-foreground">Workspace</dt>
          <dd>{membership.workspace.name}</dd>
          <dt className="text-muted-foreground">Your role</dt>
          <dd>{ROLE_LABEL[membership.role]}</dd>
        </>
      )}
    </dl>
  );
}
