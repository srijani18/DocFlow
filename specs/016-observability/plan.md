# F16: Observability (plan)

**Status:** Approved (2026-10-27)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Settings

| Variable | Where | Secret | Default |
|---|---|---|---|
| `SENTRY_DSN` | api, worker | yes | unset: off |
| `NEXT_PUBLIC_SENTRY_DSN` | web | no (public by design) | unset: off |
| `SENTRY_ENVIRONMENT` | api, web | no | `local` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | api, worker | yes (secret key) | unset: off |
| `LANGFUSE_HOST` | api, worker | no | `https://cloud.langfuse.com` |

The release is the git commit, set at build time: `RENDER_GIT_COMMIT` and `VERCEL_GIT_COMMIT_SHA`.

## 2. Components

```
app/core/observability.py   init_sentry(settings), report_exception(exc, **ids), scrub_event; tags
                            request_id/workspace/document/job from structlog contextvars or the job
app/llm/tracing.py          LangfuseTracer: CallRecord -> trace-create + generation-create events,
                            batched in the background through the SDK's ingestion API
app/llm/recording.py        DbCallRecorder hands each stored call to the tracer (CallTracer protocol)
apps/web                    instrumentation.ts + instrumentation-client.ts (Sentry.init with the
                            beforeSend scrubber), global-error.tsx, QueryCache/MutationCache onError;
                            all off when NEXT_PUBLIC_SENTRY_DSN is unset
```

The tracer hooks the existing `CallRecord`, which is already the one place every attempt is described (F10). So tracing adds no new call sites in the gateway, and evals (which use `MemoryCallRecorder` with no tracer) stay untraced.

### As built (2026-10-27)

- **Pinned versions** (the newest at least 2 weeks old, D4): `sentry-sdk` 2.72.0, `@sentry/nextjs` 11.7.0, `langfuse` 4.17.0 (every 5.x release was less than 2 weeks old).
- **Sentry reports explicitly; its auto-instrumentation is off.** Our own code already catches every unexpected error in three places: the last-resort 500 in `RequestContextMiddleware`, `job_crashed` and `worker_loop_error`. Each calls `report_exception`. Expected outcomes (4xx, `StepError` retries, permanent step failures, a 503 while the database is down) never reach those places, so AC3 holds by construction, and nothing is reported twice. Our structlog output goes to stdout, not stdlib logging, so Sentry's logging hook wouldn't have seen it anyway.
- **Langfuse through the SDK's ingestion client, not its OpenTelemetry tracer.** `CallRecord`s describe calls that have already finished. The tracer's `start_observation` stamps "now" as the start, while ingestion events take each call's real `start_time`/`end_time`. It also doesn't install a global OpenTelemetry tracer provider in the API process.
- **Web:** no `withSentryConfig`, so no source-map upload (that would need a Sentry auth token in the Vercel build). Browser stack traces are minified; server ones are not. Failed queries and mutations are reported unless they are 4xx or a cold start (`isTransient`).
- `make sentry-check` sends one scrubbed test error, for the live check.

## 3. Scrubbing (AC7)

`before_send` drops:
- `request.data`, `request.cookies` and `request.query_string`;
- `Authorization` and `X-Api-Key`-like headers.

It then walks `extra`, `contexts` and breadcrumbs, and replaces:
- values whose keys the log redactor treats as sensitive (`authorization`, `email`, or keys containing `token`, `secret`, `api_key`, `dsn`);
- values under document-content keys (`data`, `text`, `snippet`, `q`);
- any string that looks like a provider key (`AIza…`, `gsk_…`, `sk-or-…`). The web `beforeSend` does the same for `request` and breadcrumb URLs.

## 4. Testing

- **Unit:**
  - the scrubber with a crafted event (AC7);
  - the ignore rules (AC3);
  - the tracer maps a `CallRecord` to an observation with only the allowed fields (AC5);
  - the no-op path when unset (AC8).
- **Integration:** a crashing job reports once, with the job and document tags (using a fake transport); a 404 doesn't.
- **Live (end of project, with the deploy):** a deliberate error appears in Sentry; one document's trace appears in Langfuse. This is part of the deploy checklist, since the user deploys only when everything is built.
