"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";

async function fetchHealth(): Promise<"ok"> {
  const { error, response } = await api.GET("/healthz", { cache: "no-store" });
  if (error !== undefined || !response.ok) {
    throw new Error(`Health check failed with ${response.status}`);
  }
  return "ok";
}

export function ApiStatus() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: fetchHealth });

  const label = health.isPending ? "checking…" : health.isSuccess ? "ok" : "unavailable";
  return (
    <p className="text-sm text-muted-foreground" aria-live="polite">
      API: {label}
    </p>
  );
}
