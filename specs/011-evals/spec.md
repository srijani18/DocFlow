# F11: Eval suite (spec)

**Status:** Draft (2026-10-26)
**Phase:** 2
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

DocFlow claims to extract documents accurately; F11 measures it. A labelled dataset of public receipts and synthetic Indian invoices, receipts and purchase orders is run through classification and extraction. Every field is scored by the rule its schema declares, and the result is a report: accuracy per field and per document type, cost and latency, compared across models and prompt versions. It runs locally, nightly in CI, and on request on a pull request. Phase 2 is done when we have a baseline accuracy number and a model comparison table.

## User stories

- **US1:** As the operator, I want one command that measures extraction accuracy on a fixed dataset, so that I can quote real numbers (constitution §5.6).
- **US2:** As the operator, I want to compare models and prompt versions side by side, so that routing and prompt changes are decided by data.
- **US3:** As a reviewer of a pull request that changes prompts, schemas or routes, I want the eval report posted on the PR, so that regressions are visible before merging.

## Acceptance criteria

- **AC1:** A versioned dataset exists in the repo:
  - at least 20 labelled documents covering invoices, receipts and purchase orders, as PDFs and as photo-like images;
  - each with ground truth in the schema's format, plus the expected document type;
  - only public-licensed or synthetic content (constitution §5.5).
- **AC2:** Each labelled field is scored by its schema's `x-eval` rule:
  - `exact`: equal after trimming and Unicode NFC;
  - `fuzzy`: normalised similarity of at least 0.85;
  - `numeric:<tolerance>`: absolute difference within the tolerance.

  Fields the ground truth doesn't label are not scored. Line items are compared by position.
- **AC3:** WHEN an eval run finishes, THEN it reports:
  - classification accuracy;
  - field accuracy overall, per field and per document type;
  - the share of documents with every field correct;
  - the invalid-answer rate;
  - median and p95 latency, and estimated cost per document;
  - all per model and prompt version.
- **AC4:** WHEN several models are given, THEN the report includes a side-by-side comparison table on the same documents.
- **AC5:** Each run gets a stable id and is saved as JSON plus a readable Markdown report under `evals/reports/`. Any accuracy figure quoted in the README cites a run id (constitution §5.6).
- **AC6:** A run is reproducible: the dataset version, prompt versions, schema ids, models and the code commit are recorded in the report. Evals never use the response cache.
- **AC7:** In CI, evals run nightly, on demand, and on pull requests labelled `eval`, on a sample of at most 20 documents. On a pull request the Markdown report is posted as a comment. Without API keys the job skips with a clear message instead of failing.
- **AC8:** An eval run is isolated from product data: it creates no documents and needs no database.

## Edge cases

- **A provider fails mid-run:** that document is recorded as an error for that model (it counts as wrong), and the run continues.
- **Free-tier daily limits:** the CI sample size and model list are configured so a nightly run stays well inside them. OpenRouter is excluded from scheduled runs (50 requests/day).
- **Ground truth with nulls:** a `null` label means "not on the document"; the model must return `null` to score.
- **Different number of line items:** missing or extra items score as wrong for their fields.

## Non-goals

- Learning from production corrections (F7 adds corrections to the dataset).
- Statistical significance testing beyond reporting the sample size.
- Evaluating the validation agent (F6, Phase 3: before and after accuracy).

## Decisions (proposed defaults; approve or change)

- **D1. Dataset:** the first 10 receipts of the CORD v2 test split (CC BY 4.0, from Hugging Face `naver-clova-ix/cord-v2`), mapped to `receipt.v1` for the fields CORD labels (line items, subtotal, tax, total), plus 20 synthetic documents (8 invoices, 6 receipts, 6 purchase orders). Half of the synthetic ones are rendered as noisy, slightly rotated JPEG "photos". SROIE is left out because its licence is unclear.
- **D2. Where things live:** the runner is a Python package at `apps/api/evals/` (linted and type-checked with the API, using the same gateway and schemas). Data and reports live in the repo-root `evals/` folder, as the brief laid out.
- **D3. Reports are files, not a database table.** CI has no persistent database. Committed JSON reports are the record, and their ids are what the README cites. This replaces the `eval_runs` table in overview §11. F7's production corrections will be a table.
- **D0. Keys for evals:** evals run outside any workspace, so they use the **operator's** keys from the environment (`GEMINI_API_KEY`, `GROQ_API_KEY`), read only by the eval CLI and CI, never by the app (F15 D4).
- **D4. CI comparison set:** `gemini:gemini-flash-lite-latest` and `groq:meta-llama/llama-4-scout-17b-16e-instruct`, 20 documents each, nightly at 02:00 IST. GitHub secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`.
- **D5. Fuzzy threshold:** 0.85 (`difflib` ratio after case-folding and collapsing whitespace). There's no new dependency.
