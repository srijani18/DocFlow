/**
 * Error reporting with Sentry (F16 AC2, AC7, AC8). Off unless NEXT_PUBLIC_SENTRY_DSN is set.
 *
 * Every event goes through `scrubEvent` first: it keeps the stack trace and the route, never
 * tokens, AI keys, email addresses, query strings or document content.
 */
import type { Breadcrumb, ErrorEvent } from "@sentry/nextjs";

import { ApiError, isTransient } from "@/lib/api/transient";

const REDACTED = "[REDACTED]";
// Keys whose values are secrets, personal data or a document's content (as on the API).
const SENSITIVE_KEY = /authorization|cookie|email|password|token|secret|api_?key|dsn/i;
const CONTENT_KEYS = new Set(["data", "text", "snippet", "q", "query_string", "body"]);
const SECRET_PATTERNS = [
  /AIza[0-9A-Za-z_-]{20,}/g, // Google AI
  /gsk_[0-9A-Za-z]{20,}/g, // Groq
  /sk-or-[0-9A-Za-z-]{20,}/g, // OpenRouter
  /Bearer\s+[0-9A-Za-z._~+/=-]+/gi,
  /eyJ[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+/g, // JWTs, e.g. a Supabase session
  /[\w.+-]+@[\w-]+\.[\w.-]+/g, // email addresses
];
// Usage counts contain "token" but aren't secrets.
const NOT_SENSITIVE = new Set(["input_tokens", "output_tokens"]);

export function sentryOptions(dsn: string | undefined) {
  return {
    dsn,
    enabled: Boolean(dsn),
    environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? process.env.NODE_ENV,
    release: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA,
    tracesSampleRate: 0, // errors only (spec D1)
    sendDefaultPii: false,
    beforeSend: (event: ErrorEvent) => scrubEvent(event),
    beforeBreadcrumb: (breadcrumb: Breadcrumb) => scrubBreadcrumb(breadcrumb),
  };
}

/** Whether a failed query or mutation is a bug worth reporting (AC2, AC3): not a 4xx, and
 * not the backend waking up or briefly unreachable. */
export function shouldReport(error: unknown): boolean {
  if (isTransient(error)) return false;
  if (error instanceof ApiError) return error.status >= 500;
  return true;
}

function withoutQuery(url: string): string {
  const cut = url.search(/[?#]/);
  return cut === -1 ? url : url.slice(0, cut);
}

export function scrub(value: unknown, key = ""): unknown {
  if (key && !NOT_SENSITIVE.has(key) && (SENSITIVE_KEY.test(key) || CONTENT_KEYS.has(key))) {
    return REDACTED;
  }
  if (Array.isArray(value)) return value.map((item) => scrub(item));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrub(v, k)]));
  }
  if (typeof value === "string") {
    const clean = key === "url" || key === "from" || key === "to" ? withoutQuery(value) : value;
    return SECRET_PATTERNS.reduce((text, pattern) => text.replace(pattern, REDACTED), clean);
  }
  return value;
}

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  const scrubbed = scrub(event) as ErrorEvent;
  delete scrubbed.user; // the session's email and id never leave
  return scrubbed;
}

export function scrubBreadcrumb(breadcrumb: Breadcrumb): Breadcrumb | null {
  // Console output can include whatever a component logged; it isn't needed to debug.
  if (breadcrumb.category === "console") return null;
  return scrub(breadcrumb) as Breadcrumb;
}
