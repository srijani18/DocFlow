# F16: Observability (spec)

**Status:** Approved (2026-10-27)
**Phase:** 5
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

When DocFlow is deployed, the operator needs to know about errors before users report them, and to follow what the AI calls did without opening the database. This feature does two things:

- It sends **errors** from the API, the worker and the web app to an error tracker.
- It sends a **trace of every AI call** (task, model, tokens, cost, latency, outcome, fallbacks) to an LLM observability service.

Both are optional. Without their settings, DocFlow runs exactly as now. Neither ever receives document contents, extracted values, AI keys or personal data.

## User stories

- **US1:** As the operator, I want unhandled errors reported with a stack trace and the request id, so that I can fix them quickly.
- **US2:** As the operator, I want to see each document's AI calls as one trace (classify → extract → validate → embed), with timings and fallbacks, so that I can explain slow or failed processing.
- **US3:** As a workspace owner, I want my documents and data never to reach a third-party monitoring service, so that I can trust DocFlow with them.

## Acceptance criteria

### Errors

- **AC1:** WHEN the API or the worker raises an unhandled error (a 500, or a job that crashed), THEN it is reported with the stack trace, the release, the environment, and the `request_id`, `workspace_id`, `document_id` and `job_id` where known.
- **AC2:** WHEN the web app hits an unhandled error (a render error or a failed fetch other than 4xx), THEN it is reported with the route and release. It is never reported with the user's email, token or page content.
- **AC3:** Expected errors are not reported: 4xx responses, validation problems, a provider being temporarily unavailable, a job retry.

### AI call traces

- **AC4:** Every gateway attempt (F10) becomes an observation in a trace per job (one trace per document processing run, or per search query). It records the task, provider, model, prompt version, route position, input mode, tokens, estimated cost, latency, outcome and error type: the same fields as `llm_calls` (constitution §5.2).
- **AC5:** Traces carry **no inputs or outputs**: no prompt text, file, extracted data or query text. Only ids (workspace, document, job) and the fields of AC4.
- **AC6:** Sending traces never slows or fails processing. They are batched in the background, and if the service is unreachable they are dropped, with a warning in the log.

### Privacy and configuration

- **AC7:** A scrubber removes from every error event:
  - request bodies, cookies, `Authorization` headers and query strings;
  - any value under the keys the log redactor already treats as sensitive (constitution §6.5).

  A test sends an event containing an AI key, an email and an extracted amount, and checks that none of them leave.
- **AC8:** Error tracking and tracing are each turned on by their own settings, and are off when those are missing (local development and CI). The settings are listed in `.env.example` and the deploy guide.
- **AC9:** Both run on free tiers. Sampling is set so that a demo deployment stays within them.

## Edge cases

- **The same error repeating in a loop** (the database down): grouped by the tracker; the worker's existing pause prevents a flood.
- **Cache hits:** recorded as observations with cost $0.
- **Evals:** they never send traces, since they run outside the app.

## Non-goals

- Metrics dashboards in the monitoring tools (F13 is the product's metrics).
- Logs shipping (Render keeps the JSON logs).
- Uptime checks (the deploy guide's cron ping covers keep-alive).
- Prompt management or evals in the LLM tool.

## Decisions

- **D1. Sentry for errors** (Developer plan: 5,000 errors a month, 1 user), with `sentry-sdk` for FastAPI and the worker, and `@sentry/nextjs` for the web app. Performance tracing is off (errors only), to stay in the free tier and keep it simple.
- **D2. Langfuse Cloud for AI traces** (Hobby plan: 50,000 units a month). It's open source, with an official Python SDK, and the overview and ADR-0003 already name it. At about 4 observations per document, 50,000 units is roughly 10,000 documents a month.
- **D3. Metadata only (AC5).** Langfuse usually stores prompts and outputs. We deliberately don't, because they are customers' documents processed with customers' own keys (ADR-0008). Debugging a specific answer is done locally with the eval tools instead.
- **D4. Pinned SDK versions** are the newest releases at least two weeks old at implementation time.
