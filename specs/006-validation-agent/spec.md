# F6: Validation agent (spec)

**Status:** Draft (2026-10-26)
**Phase:** 3
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

After extraction, a validation agent checks the extracted data the way an accounts clerk would:
- do the line items add up to the subtotal, and the subtotal plus taxes to the total?
- is each GSTIN real (format and checksum)?
- do the dates make sense?
- is this a duplicate of a document we already have?
- is the vendor one we've seen before?

When a check fails on something the model may simply have misread, the agent asks the model to look at the document again for those specific fields, a limited number of times. Every fix is recorded as a new extraction version. Documents that pass everything with high confidence are approved automatically; the rest go to a person with the problems listed.

## User stories

- **US1:** As a reviewer, I want obvious extraction mistakes (sums that don't add up, a misread GSTIN digit) fixed before I see the document, so that I spend my time on real judgement calls.
- **US2:** As a reviewer, I want every remaining problem listed with the fields it concerns, so that I know exactly what to check.
- **US3:** As an admin, I want clean, confident documents approved without anyone opening them, so that review effort goes where it's needed.
- **US4:** As the operator, I want to measure accuracy before and after the agent, so that I can show what it adds (Phase 3 "done when").

## Acceptance criteria

### Checks

- **AC1:** WHEN a document has been extracted, THEN its status becomes `VALIDATING` and these checks run on the current extraction:
  - **Line items:** each line's quantity × unit price equals its amount, and the line amounts add up to the subtotal.
  - **Totals:** the subtotal plus taxes equals the total.
  - **GSTIN:** every GSTIN present has a valid format *and* checksum.
  - **Tax type:** CGST and SGST are used together, and they aren't mixed with IGST.
  - **Dates:** not in the future; due or delivery dates aren't before the document date; nothing before 2000.
  - **Duplicate:** another document in the workspace has the same vendor GSTIN (or vendor name) and the same document number.
  - **Known vendor:** the vendor has appeared on an earlier approved document in the workspace (informational).

  Amounts match within ₹1.00, or 0.5% of the larger amount, whichever is greater.
- **AC2:** Each failed check is recorded as an issue with the check name, a severity (`error`, `warning` or `info`), the field paths involved, a readable message, and whether the agent fixed it.

### Fixing

- **AC3:** WHEN a check fails in a way that rereading could fix (arithmetic or an invalid GSTIN checksum), THEN the agent asks the model to reread the document for the fields involved. It explains what failed and gives the current values. Any corrected values that make the checks pass are saved as a new extraction version from the agent (`source = agent_fix`), with a confidence for each corrected field.
- **AC4:** The agent makes at most 2 fixing rounds per document, and stops early when a round changes nothing or all checks pass. A correction that makes the checks worse is discarded.
- **AC5:** Duplicates, unknown vendors, tax-type mixes and date problems are never "fixed" by the model. They are reported for a person, because rereading can't settle them.

### Outcome

- **AC6:** WHEN validation finishes with no `error` or `warning` issues and every field's confidence is at least 0.90, THEN the document is `APPROVED` automatically (recorded as approved by the agent). Otherwise it goes to `NEEDS_REVIEW`.
- **AC7:** A document flagged as a possible duplicate is never auto-approved.
- **AC8:** Every model call the agent makes goes through the gateway and is logged (constitution §5.1, §5.2), as task `validate`.
- **AC9:** Running validation again for the same processing run doesn't add new versions or duplicate issues (F3 AC6).

### Measurement

- **AC10:** The eval suite can run with the agent on. The report shows field accuracy before and after the agent per model, plus how often the agent changed a field from right to wrong.

## Edge cases

- **No line items or no taxes printed:** the related checks are skipped, not failed.
- **Rounding on invoices** (for example ₹0.49 rounding lines): covered by the tolerance in AC1.
- **Receipts without GSTIN:** nothing to check.
- **Foreign currency:** the arithmetic checks still apply; the GST checks are skipped when the currency isn't INR.
- **The model "fixes" a value into something worse:** discarded (AC4).
- **Provider unavailable during a fixing round:** the document goes to `NEEDS_REVIEW` with its issues; the agent's work is best-effort and never fails the document.

## Non-goals

- External lookups (the government GSTIN API, vendor master data). The checksum is local.
- Learning from corrections (F7 feeds the eval set; prompt changes stay manual and are measured).
- Custom per-workspace rules.

## Decisions (proposed defaults; approve or change)

- **D1. Checks are deterministic Python "tools"; the model only rereads.** The agent loop is: run the tools, decide what's fixable, ask the model for corrected values of specific fields (structured output), re-run the tools, and keep the correction only if it helps. This is provider-agnostic, testable without an LLM, and easy to explain. Free-form function calling isn't used, because it differs across Gemini, Groq and OpenRouter.
- **D2. Thresholds:** ₹1.00 or 0.5% tolerance; auto-approve at confidence ≥ 0.90 with no errors or warnings; 2 fixing rounds.
- **D3. Dataset v2:** synthetic GSTINs are regenerated with **valid checksums** (v1's were random), and 4 deliberately broken synthetic documents are added (wrong total, misprinted GSTIN digit, duplicate number, CGST+IGST mix), so the agent's catches are measurable.
- **D4. Model for rereading:** the extract route (Flash-Lite first, with fallback), with prompt `validate/v1`.
