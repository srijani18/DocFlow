# F7: Human review (tasks)

**Status:** Implemented (2026-10-26)
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
- [x] **F7-T7: Live check and close-out:** fix and approve a sample with an error; check the corrections and the metric; spec status `Implemented`.
  - **Done (2026-10-26), locally with Gemini Flash-Lite, in a real browser:**
    1. `broken-invoice-wrong-total.pdf` went through classify → extract → validate. The agent asked the model to reread the total, and the model correctly reported nothing misread: the total is printed wrong. The document went to review with a `totals` error.
    2. In review, the reviewer corrected the total from 3524.95 to 3424.95 and approved.
    3. The result: version 2 (`human`), one correction row (`total.amount`), the `totals` error gone from version 2, and `APPROVED` with the approved version recorded. The dashboard shows "Approved without edits: 0% (0 of 1)".
  - The PDF pane was blank only in headless Chromium, which has no PDF viewer. The signed URL is served as `application/pdf` with no framing restrictions.
