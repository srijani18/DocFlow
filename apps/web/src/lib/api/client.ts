import createClient from "openapi-fetch";

import { env } from "@/env";
import type { paths } from "@/generated/api";

// Typed client generated from apps/api/openapi.json (`make gen`). F1 adds auth middleware.
export const api = createClient<paths>({
  baseUrl: env.NEXT_PUBLIC_API_BASE_URL,
  // Resolve fetch at call time so tests (and future instrumentation) can replace it.
  fetch: (request) => globalThis.fetch(request),
});
