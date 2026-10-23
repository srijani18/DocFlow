"use client";

import { useQuery } from "@tanstack/react-query";

import { env } from "@/env";

async function fetchHealth(): Promise<"ok"> {
  const response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/healthz`, { cache: "no-store" });
  if (!response.ok) {
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
