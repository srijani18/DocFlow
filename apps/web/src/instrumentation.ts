import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "@/lib/observability";

/** Server-side errors in rendering and route handlers (F16 AC2). Off without a DSN. */
export function register() {
  if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
    Sentry.init(sentryOptions(process.env.NEXT_PUBLIC_SENTRY_DSN));
  }
}

export const onRequestError = Sentry.captureRequestError;
