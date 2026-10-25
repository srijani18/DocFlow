# F3: Processing pipeline (tasks)

**Status:** Approved (2026-10-25)
**Prerequisite:** F2-T2 (tables).

- [x] **F3-T1: Jobs and events tables, status transitions** (AC2) — migration `0004_jobs`, `transition()` with compare-and-set and `document_events`.
  - Tests: `test_ac2_transition_records_event_and_timestamp`, `test_ac2_transition_from_wrong_status_rejected`. **Done when:** `make migrations-check` passes; tenant meta-test passes.
- [x] **F3-T2: Queue repository** (AC3, AC4, AC5) — claim, finish, retry later, kill; backoff with jitter.
  - Tests: `test_ac5_two_claimers_never_get_same_job`, `test_ac5_expired_lease_is_reclaimed`, `test_ac5_stale_worker_cannot_finish_reclaimed_job`, `test_ac3_backoff_doubles_with_cap_and_retry_after`, `test_ac3_dead_after_five_attempts`.
- [x] **F3-T3: Pipeline runner and fetch step** (AC1, AC4, AC6, AC7) — steps interface, error classes, download + hash check. Classify/extract are stubs until F4/F5.
  - Tests: `test_ac7_hash_mismatch_fails_permanently`, `test_ac4_permanent_error_no_retry`, `test_ac6_rerun_skips_finished_steps`.
- [x] **F3-T4: Worker loop** (AC1, AC11, AC12) — wake event from upload completion, sleep until next `run_after`, 5-minute sweep.
  - Tests: `test_ac1_completed_upload_is_processed`, `test_ac11_idle_worker_runs_no_queries`, `test_ac12_queued_jobs_run_after_restart`.
- [x] **F3-T5: Retry endpoint** (AC8) — `POST …/documents/{id}/retry`.
  - Tests: `test_ac8_retry_failed_document_requeues_with_fresh_attempts`, `test_ac8_retry_non_failed_is_409`, `test_ac8_double_retry_one_job`, `test_ac10_retry_other_workspace_404`.
- [x] **F3-T6: Event broker and SSE endpoint** (AC9, AC10) — publish after commit; keep-alive; 30-minute close.
  - Tests: `test_ac9_status_change_streamed`, `test_ac10_other_workspace_events_not_streamed`, `test_sse_keepalive_and_max_duration`. **Done when:** `make check-gen` clean.
- [x] **F3-T7: Web live status** (AC8, AC9) — `lib/api/events.ts`, `use-document-events`, status badge, retry button.
  - Tests: `AC9: list updates when a status event arrives`, `AC9: reconnects after the stream drops`, `AC8: retry button shown only for FAILED`.
- [x] **F3-T8: Close-out** — local end-to-end: upload → statuses advance live (with stub steps until F4/F5); spec status `Implemented`.
