# F7: Human review (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F6.

- [ ] **F7-T1: Corrections table and diff** (AC4): migration `0010_corrections`, server-side diff by path.
- [ ] **F7-T2: Save and approve endpoints** (AC4–AC7): version check, schema validation, checks re-run, `accept_errors`.
- [ ] **F7-T3: Schema endpoint and metrics** (AC8): `GET /v1/schemas/{id}`, review metrics.
- [ ] **F7-T4: Review page**: viewer, schema form, live validation, problems list, Next problem, approve and conflict handling (AC1–AC3, AC5, AC6).
- [ ] **F7-T5: Dashboard metric** (AC8): "Approved without edits".
- [ ] **F7-T6: Eval import CLI** (AC9): `make eval-import WORKSPACE=<id>`.
- [ ] **F7-T7: Live check and close-out:** fix and approve a sample with an error; check the corrections and the metric; spec status `Implemented`.
