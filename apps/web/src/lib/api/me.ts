"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { ApiError, createColdStartRetry, toApiError } from "@/lib/api/transient";

export type Me = components["schemas"]["Me"];

async function fetchMe(): Promise<Me> {
  const { data, error, response } = await api.GET("/v1/me");
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

/**
 * The signed-in user and their memberships. The first API call after a cold start, so it
 * carries the 90-second retry policy (F1 AC20).
 */
export function useMe() {
  // One retry policy per mounted component: it tracks when the current fetch first failed.
  const [coldStartRetry] = useState(() => createColdStartRetry());
  return useQuery({ queryKey: ["me"], queryFn: fetchMe, ...coldStartRetry });
}

/** F1 gives each user one personal workspace; switching workspaces is a non-goal. */
export function currentWorkspace(me: Me) {
  return me.memberships[0];
}

export { ApiError };
