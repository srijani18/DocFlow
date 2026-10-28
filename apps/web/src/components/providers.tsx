"use client";

import * as Sentry from "@sentry/nextjs";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { shouldReport } from "@/lib/observability";

function report(error: unknown) {
  if (shouldReport(error)) Sentry.captureException(error);
}

export function createQueryClient() {
  // Failed API calls other than 4xx and cold starts are reported (F16 AC2, AC3); a no-op
  // without a DSN.
  return new QueryClient({
    queryCache: new QueryCache({ onError: report }),
    mutationCache: new MutationCache({ onError: report }),
  });
}

export function Providers({ children }: { children: ReactNode }) {
  // One client per browser session; created lazily so it is never shared across requests.
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
