# F16: Observability (plan)

**Status:** Draft (2026-10-27)
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
app/core/observability.py   init_sentry(settings): FastAPI + asyncio integrations, before_send scrubber,
                            ignore 4xx/StepError/TransientError; tags request_id/workspace/document/job
                            from structlog contextvars
app/llm/tracing.py          Tracer protocol (no-op default) + LangfuseTracer: on_attempt(CallRecord)
                            → observation in trace keyed by job_id (or a per-request id for search)
app/llm/recording.py        CallRecorder fans out to the tracer after the DB/memory record
apps/web                    instrumentation.ts + sentry.client/server config with beforeSend scrubber,
                            only when NEXT_PUBLIC_SENTRY_DSN is set
```

The tracer hooks the existing `CallRecord`, which is already the one place every attempt is described (F10). So tracing adds no new call sites in the gateway, and evals (which use `MemoryCallRecorder` with no tracer) stay untraced.

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
