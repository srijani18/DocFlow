# F11: Eval suite (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F10-T5 (gateway loop). Manual: GitHub secrets `GEMINI_API_KEY`, `GROQ_API_KEY` for CI evals.

- [x] **F11-T1: Gateway hooks** (AC6, AC8): `CallRecorder` (DB and memory), `use_cache`, explicit routes.
  - Tests: `test_ac8_memory_recorder_needs_no_database`, `test_ac6_eval_requests_bypass_cache`.
- [x] **F11-T2: Dataset** (AC1): synthetic generator (20 documents, half as photo-like JPEGs) and CORD import of 10 receipts with mapping and masks; `manifest.v1.json`.
  - Tests: `test_ac1_manifest_valid_files_exist_licences_present`, `test_ac1_every_truth_validates_against_its_schema`, `test_ac1_covers_three_types_and_both_formats`.
- [x] **F11-T3: Scoring** (AC2)
  - Tests: `test_ac2_exact_normalises_whitespace_and_nfc`, `test_ac2_fuzzy_threshold`, `test_ac2_numeric_tolerance`, `test_ac2_nulls_must_match`, `test_ac2_line_items_by_index`, `test_ac2_unlabelled_paths_skipped`.
- [x] **F11-T4: Runner and report** (AC3–AC6)
  - Tests: `test_ac3_aggregates`, `test_ac4_comparison_table`, `test_ac5_run_id_and_files`, `test_ac6_report_records_versions`, `test_full_run_with_fake_provider`.
- [x] **F11-T5: CI workflow** (AC7): `evals.yml`, `make eval`, skip without keys, PR comment.
  - **Done when:** a `workflow_dispatch` run produces an artifact (or skips cleanly without secrets).
- [ ] **F11-T6: Baseline (Phase 2 done when)** (AC5): a real run of both models on the dataset, with the report committed; the README cites the run id with the baseline accuracy and the comparison table. Spec status `Implemented`.
