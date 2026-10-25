# F4: Classification (spec)

**Status:** Approved (2026-10-25)
**Phase:** 1
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

The first AI step of the pipeline (F3) decides what kind of document was uploaded: an invoice, a receipt, a purchase order, or something else. The answer decides which extraction schema F5 uses. This feature also introduces the minimal LLM gateway and the log of every LLM call, which F5 reuses and F10 later extends with more providers and fallback.

## User stories

- **US1:** As a member, I want each document's type detected automatically, so that the right fields are extracted.
- **US2:** As a member, I want to see the detected type and how sure the system is, so that I can spot mistakes.
- **US3:** As the operator, I want every AI call recorded with its model, prompt version, tokens, estimated cost and latency, so that cost and speed can be measured (overview §11).

## Acceptance criteria

- **AC1:** WHEN a document reaches the classification step, THEN it is labelled `invoice`, `receipt`, `purchase_order` or `other`, with a confidence from 0 to 1, and the label and confidence are shown on the document list and detail page.
- **AC2:** WHEN the AI's answer doesn't match the classification schema (`schemas/classification.v1.json`), THEN that attempt counts as failed and is retried like any temporary error (F3 AC3). An invalid answer is never stored.
- **AC3:** WHEN a document is labelled `other`, THEN extraction is skipped and the document goes to `NEEDS_REVIEW` with the note "Not an invoice, receipt or purchase order".
- **AC4:** Every AI call, whether it succeeded, failed or returned an invalid answer, is recorded with: workspace, document, task, provider, model, prompt version, input and output tokens, estimated cost, latency, outcome and attempt number (constitution §5.2).
- **AC5:** WHEN the AI provider rate-limits, times out or errors, THEN the step fails as a temporary error, honouring any "retry after" the provider gives (F3 AC3).
- **AC6:** The model and the prompt version used are configuration and versioned files, not code. Changing the prompt means adding a new version (constitution §5.3, §5.7).
- **AC7:** Running classification again for a document that already has a label (F3 AC6) makes no new AI call.

## Edge cases

- **Image of a receipt photographed at an angle, or a scanned PDF:** handled by the vision model; low confidence is shown, not hidden.
- **Low confidence (below 0.6):** the document still proceeds with the most likely label; the detail page shows the confidence.
- **A multi-document PDF** (e.g. three invoices in one file): classified as one document, by its first pages. Splitting is a non-goal.
- **An empty or blank page:** usually `other`.

## Non-goals

- Fallback to other providers, circuit breaker, response cache (F10).
- Changing the type by hand (F7).
- More document types.

## Decisions (approved 2026-10-25)

- **D1. Gemini, not Groq, classifies in Phase 1.** The brief suggested Groq for classification, but the input is a PDF or image: Groq's models can't read PDFs, and the Phase 1 row of the brief says "Gemini only". F10 can route image classification to Groq later.
- **D2. Models:** `gemini-flash-lite-latest` for classification, as configuration. The real model list and free-tier limits are read from AI Studio with your key during implementation and recorded in overview §8.
- **D3. Cost:** estimated from a versioned price table in the repo (list prices per million tokens), so "cost per document" is meaningful even though free-tier spend is $0.
