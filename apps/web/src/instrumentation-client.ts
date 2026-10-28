import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "@/lib/observability";

// Browser errors (F16 AC2). Without NEXT_PUBLIC_SENTRY_DSN this initialises nothing.
if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init(sentryOptions(process.env.NEXT_PUBLIC_SENTRY_DSN));
}
