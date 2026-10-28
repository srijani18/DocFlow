# F6: Validation agent (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F5, F10, F11.

- [x] **F6-T1: GSTIN, money and checks** (AC1, AC2, AC5): pure functions and test vectors.
- [x] **F6-T2: Statuses and tables** (AC2, AC6): migration `0009_validation`, `VALIDATING` and `APPROVED`, approval columns, `validate` task.
- [x] **F6-T3: Agent loop and prompt** (AC3, AC4, AC8): `validate/v1`, fake-model tests for fix, no progress, worse result and round limit.
- [x] **F6-T4: Validate step** (AC1, AC6, AC7, AC9): pipeline wiring, auto-approve, duplicate and known-vendor checks against the workspace, idempotency.
  - Tests: `tests/integration/jobs/test_validation.py` (approved by the agent, low confidence, misread total fixed as an `agent_fix` version, unfixable misread, provider down, duplicate, workspace isolation, re-run).
  - Note: "today" for the future-date check is the latest calendar date anywhere (UTC+14), so a document dated today in any time zone passes.
- [x] **F6-T5: API and UI**: issues endpoint, issue counts on `Document`, an "Approved" badge and issue list on the detail page.
- [ ] **F6-T6: Dataset v2 and evals with the agent** (AC10): valid GSTIN checksums, 4 broken documents, the `--agent` flag, a before/after report.
- [ ] **F6-T7: Live check and close-out:** process the broken samples locally, then commit the before/after eval run (Phase 3 "done when", together with F7).
