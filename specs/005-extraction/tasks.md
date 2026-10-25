# F5: Structured extraction (tasks)

**Status:** Approved (2026-10-25)
**Prerequisite:** F4-T2 (gateway).

- [x] **F5-T1: Schemas, codegen and samples** (AC2) — `schemas/common`, `schemas/documents/*.v1.json`, `classification.v1.json` (from F4) and the envelope; `make gen-schemas` wired; `evals/samples/generate_synthetic.py` and the generated samples.
  - Tests: `test_ac2_schemas_valid_draft_2020_12`, `test_ac2_examples_validate`, `test_ac2_bad_gstin_rejected`, `test_ac2_every_property_required_and_nullable`. **Done when:** `make check-gen` clean.
- [x] **F5-T2: Schema registry and envelope validation** (AC3) — bundle by `schema_id`, confidence-path check, Decimal parsing.
  - Tests: `test_ac3_unknown_confidence_path_invalid`, `test_ac3_confidence_out_of_range_invalid`, `test_ac8_amounts_parsed_as_decimal`.
- [x] **F5-T3: Extractions table and repository** (AC4, AC7) — migration `0006_extractions`, append-only insert, summary columns.
  - Tests: `test_ac4_versions_append_only`, `test_ac7_summary_columns_per_type`. **Done when:** migrations-check and tenant meta-test pass.
- [x] **F5-T4: Extract step and prompt** (AC1, AC3, AC5) — `prompts/extract/v1.md`, step wiring after classify.
  - Tests: `test_ac1_invoice_receipt_po_extracted_to_needs_review`, `test_ac3_invalid_answer_not_stored_and_retried`, `test_ac3_fails_after_last_attempt`, `test_ac5_rerun_no_call_no_new_version`.
- [x] **F5-T5: Extraction endpoint** (AC4, AC6) — `GET …/documents/{id}/extraction`; `Document` summary fields; regenerate client.
  - Tests: `test_ac6_returns_current_extraction`, `test_other_workspace_extraction_404` (constitution §4). **Done when:** `make check-gen` clean.
- [x] **F5-T6: Web extraction view and list columns** (AC6, AC7).
  - Tests: `AC6: shows fields, line items and highlights low confidence`, `AC6: raw JSON toggle`, `AC7: list shows vendor and total`.
- [x] **F5-T7: Phase 1 done-when (local)** — upload the synthetic invoice through the UI with a real Gemini key; statuses advance live; extracted fields appear. Record cost and latency from `llm_calls` in the PR. Spec status `Implemented`.
