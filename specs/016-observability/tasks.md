# F16: Observability (tasks)

**Status:** Draft (2026-10-27)
**Prerequisite:** F10. Manual, at deploy time: a Sentry project (DSN) and a Langfuse project (keys).

- [ ] **F16-T1: Settings and Sentry for the API and worker** (AC1, AC3, AC7, AC8): init, tags, ignore rules, scrubber, tests with a fake transport.
- [ ] **F16-T2: Sentry for the web app** (AC2, AC7, AC8): Next.js instrumentation, `beforeSend` scrubber, off without DSN.
- [ ] **F16-T3: Langfuse tracer** (AC4–AC6): `Tracer` protocol, `LangfuseTracer` from `CallRecord`, background batching, never failing a call.
- [ ] **F16-T4: Docs:** `.env.example`, the deploy guide steps (Sentry and Langfuse sign-up, free-tier limits, the variables).
- [ ] **F16-T5: Live check** (deferred to the end-of-project deploy): one error in Sentry, one document trace in Langfuse.
