# F16: Observability (tasks)

**Status:** Approved (2026-10-27)
**Prerequisite:** F10. Manual, at deploy time: a Sentry project (DSN) and a Langfuse project (keys).

- [x] **F16-T1: Settings and Sentry for the API and worker** (AC1, AC3, AC7, AC8): init, tags, ignore rules, scrubber, tests with a fake transport.
- [x] **F16-T2: Sentry for the web app** (AC2, AC7, AC8): Next.js instrumentation, `beforeSend` scrubber, off without DSN.
- [x] **F16-T3: Langfuse tracer** (AC4–AC6): `Tracer` protocol, `LangfuseTracer` from `CallRecord`, background batching, never failing a call.
- [x] **F16-T4: Docs:** `.env.example`, the deploy guide steps (Sentry and Langfuse sign-up, free-tier limits, the variables).
- [ ] **F16-T5: Live check** (deferred to the end-of-project deploy): one error in Sentry, one document trace in Langfuse. Steps: deploy guide §7.
  - Done before the deploy (2026-10-27): the Langfuse request the SDK client builds was captured with an httpx mock transport. It is a POST to `/api/public/ingestion` with Basic auth, a trace keyed by the job id and a generation with start/end times, model, usage and cost, and no input or output.
