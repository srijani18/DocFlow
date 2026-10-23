# ADR-0003: Write our own LLM gateway instead of using LangChain or similar

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

We call three providers (Gemini, Groq, OpenRouter) on free tiers, where rate limits are low and change often. We need:

- routing per task (classify, extract, validate, embed),
- fallback on 429 errors and timeouts,
- a circuit breaker,
- a response cache,
- structured output against our own JSON Schemas (with `x-` keys stripped and refs inlined),
- per-call logging of tokens, cost and latency,
- a fake provider for tests,
- prompt versions that can be compared in evals.

The project exists partly to show this engineering.

## Decision

Build a small gateway in `app/llm/`:

- A `Provider` protocol with `complete(request) -> response` and `embed(texts) -> vectors`. Each provider is a thin adapter calling its HTTP API through `httpx`. We use a provider's official SDK only if that clearly saves work, and only inside `providers/`.
- A `Router` that maps each task to an ordered list of `(provider, model)` taken from configuration.
- The `Gateway`, which composes: cache lookup → circuit-breaker check → call with timeout → schema validation → fallback to the next route → logging to `llm_calls` (and later Langfuse).
- A schema adapter that inlines `$ref`s, removes `x-*` keys, and removes keywords the target provider doesn't support.
- `FakeProvider` for tests, which returns scripted responses and errors.

## Consequences

**Good:**
- Every behavior that matters (fallback order, breaker thresholds, cost accounting) is explicit code with unit tests, and easy to explain in an interview.
- No framework abstractions to work around. Provider quirks are isolated in one adapter each.
- The same gateway serves the pipeline, the agent, the evals and search embeddings, so the numbers are consistent.

**Bad:**
- We maintain the provider adapters as their APIs change. That's limited to three adapters, each covered by contract tests against recorded responses.
- The tool-calling agent loop (F6) is our own code. That's intended: it's small, and it's the part worth showing.

## Alternatives considered

- **LangChain or LlamaIndex:** large dependency trees on a 512 MB instance, opaque retry and fallback behavior, and frequent breaking changes. The brief rules them out.
- **LiteLLM as a library:** good provider coverage, but heavy, and it hides the fallback and cost logic we want to own. We could revisit it as a provider adapter behind our interface if adapter upkeep becomes costly.
- **The OpenRouter-only route:** a single API, but the free tier gives only 50 requests a day, and it creates a single point of failure.
