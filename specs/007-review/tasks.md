# F7: Human review (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F6.

- [x] **F7-T1: Corrections table and diff** (AC4): migration `0010_corrections`, server-side diff by path.
- [x] **F7-T2: Save and approve endpoints** (AC4–AC7): version check, schema validation, checks re-run, `accept_errors`.
  - Tests: `tests/integration/review/test_review_api.py`.
  - Notes:
    - Fields a reviewer changed get confidence 1.0.
    - A save that changes nothing adds no version.
    - Approving with open errors returns 409 `open-errors` until `accept_errors` is set.
- [x] **F7-T3: Schema endpoint and metrics** (AC8): `GET /v1/schemas/{id}`, review metrics.
- [x] **F7-T4: Review page**: viewer, schema form, live validation, problems list, Next problem, approve and conflict handling (AC1–AC3, AC5, AC6).
- [x] **F7-T5: Dashboard metric** (AC8): "Approved without edits".
- [x] **F7-T6: Eval import CLI** (AC9): `make eval-import WORKSPACE=<id>`.
  - Notes:
    - Exports every document a *person* approved (with or without edits): both are verified truth. Each entry records its correction count.
    - Output goes to `evals/imported/<id>/`, which is git-ignored, since it holds your own documents. Run it with `make eval MANIFEST=…`.
- [ ] **F7-T7: Live check and close-out:** fix and approve a sample with an error; check the corrections and the metric; spec status `Implemented`.
