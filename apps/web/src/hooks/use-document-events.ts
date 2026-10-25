"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { getAccessToken } from "@/lib/api/client";
import { documentKeys } from "@/lib/api/documents";
import { followEvents } from "@/lib/api/events";

/** Keeps the workspace's document queries fresh from the live status stream (F3 AC9). */
export function useDocumentEvents(workspaceId: string) {
  const queryClient = useQueryClient();
  useEffect(() => {
    const controller = new AbortController();
    // Lists and details share the ["documents", workspaceId] prefix.
    const refresh = () =>
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(workspaceId) });
    void followEvents(
      workspaceId,
      { onReady: refresh, onStatus: refresh },
      controller.signal,
      getAccessToken,
    );
    return () => controller.abort();
  }, [queryClient, workspaceId]);
}
