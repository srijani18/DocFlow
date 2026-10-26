# F10: LLM gateway with fallback (spec)

**Status:** Draft (2026-10-26)
**Phase:** 2
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

> Depends on F15 (bring your own AI keys): every provider call uses the document's workspace key.
>
> Folder numbers follow feature IDs (F10 → `010-…`) rather than build order, so a spec is easy to find from its ID.

## Summary

Phase 1 calls one provider (Gemini). Free tiers are unreliable: during the Phase 1 check, Gemini Flash timed out and returned "overloaded" for minutes at a time. F10 turns the gateway into what ADR-0003 describes. Each task has an ordered list of models across Gemini, Groq and OpenRouter. When one fails for a temporary reason, the gateway moves on to the next. A provider that keeps failing is rested for a while. Identical requests are answered from a cache. Every attempt is still logged.

## User stories

- **US1:** As a member, I want my documents processed even when one AI provider is down or rate-limited, so that a provider outage doesn't fail my uploads.
- **US2:** As the operator, I want a failing provider skipped for a while instead of called again and again, so that we don't waste time or free-tier quota on it.
- **US3:** As the operator, I want reprocessing the same file with the same prompt to cost nothing, so that retries and evals stay inside free tiers.
- **US4:** As the operator, I want to see which provider and model answered each call, and when a fallback happened, so that reliability and cost can be measured per provider.

## Acceptance criteria

- **AC1:** Each task (classify, extract) has an ordered route of provider/model pairs set in configuration. WHEN the first one succeeds, THEN no other is called.
- **AC2:** WHEN a route entry fails with a temporary error (rate limit, timeout, server error, or a provider that isn't configured) or returns an answer that fails validation, THEN the gateway tries the next entry in the same request. WHEN every entry fails, THEN the step fails as a temporary error and the queue retries it later (F3 AC3).
- **AC3:** WHEN a provider rejects the input itself (for example an unreadable file), THEN the gateway still tries the next entry, because another model may read it. WHEN every entry rejects it, THEN the step fails permanently (F3 AC4).
- **AC4:** WHEN a provider/model fails with temporary errors 3 times in a row, THEN it is skipped for 60 seconds. After that, one trial request decides whether it is used again (success) or skipped for another 60 seconds (failure). Skipping is logged.
- **AC5:** WHEN a provider can't read PDFs, THEN the gateway sends it images of the first pages instead (at most 3 pages), and the call records that conversion. Image uploads (PNG, JPEG) are sent as they are.
- **AC6:** WHEN the same request (same workspace, file content, task, prompt version, schema and model route) was answered successfully before, THEN the stored answer is returned without calling any provider, and a cache hit is logged with zero cost. Cached answers are never shared between workspaces.
- **AC7:** Every provider attempt and every cache hit is logged (constitution §5.2) with its provider, model, position in the route, and whether it was a fallback.
- **AC8:** The gateway's interface for callers doesn't change: F4 and F5 steps keep calling `generate(...)`.
- **AC9:** Keys come from the document's workspace (F15, bring your own key). Route entries for providers the workspace hasn't connected are skipped, so a workspace with only a Gemini key still works. If none of a task's providers is connected, the step fails with F15's `no_ai_key`.

## Edge cases

- **All providers rate-limited:** the queue's backoff applies, honouring the longest "retry after" any provider gave (F3).
- **A fallback model returns a lower-quality answer that is still valid:** it is accepted. Which model answered is visible in `llm_calls` and on the extraction (`prompt_version` and the call), and F11 measures each model's accuracy.
- **Circuit state after a restart:** kept in memory, so a restart forgets it. That is acceptable, because a closed circuit only costs one failed call.
- **Cache and retries:** a retry after a *failure* isn't cached (only successes are), so it calls a provider again.
- **Multi-page PDFs on image-only providers:** only the first 3 pages are sent, which is a known limit noted in the call log.

## Non-goals

- Paying for higher limits, or load-balancing across keys.
- Streaming responses.
- Embeddings (F8 adds them through the same gateway).
- A persistent (database) circuit breaker shared across instances.

## Decisions (proposed defaults; approve or change)

- **D1. Routes:**
  - Classify: `gemini:gemini-flash-lite-latest` → `groq:meta-llama/llama-4-scout-17b-16e-instruct` → `openrouter:openrouter/free`.
  - Extract: `gemini:gemini-flash-lite-latest` → `groq:meta-llama/llama-4-scout-17b-16e-instruct` → `openrouter:openrouter/free`.
  - Model IDs are configuration, verified with your keys when building.
- **D2. Circuit breaker:** opens after 3 consecutive temporary failures, stays open for 60 s, then lets one trial request through. It is kept per process, in memory, and keyed by workspace, provider and model, because each workspace has its own keys and quota (F15).
- **D3. PDF to images:** with `pypdfium2` (a small wheel that renders locally and fits in 512 MB), first 3 pages, 150 DPI PNG.
- **D4. Cache:** a Postgres table keyed by a SHA-256 of (workspace, file SHA-256, task, prompt version, schema id, route). Successful answers only; entries kept 30 days.
- **D5. OpenRouter** is last in every route, because its free tier allows only 50 requests a day (overview A6).
