# F7: Human review (spec)

**Status:** Approved (2026-10-26)
**Phase:** 3
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

A reviewer opens a document that needs review and sees the original on one side and the extracted fields on the other, as an editable form. Low-confidence fields and validation issues (F6) are highlighted, and the reviewer can jump between them. They correct what's wrong, then approve. Every correction is saved as a new extraction version, with a record of each changed field. These records feed the "approved without edits" metric and can be turned into eval data.

## User stories

- **US1:** As a reviewer, I want the original document next to the extracted fields, so that I can compare them without switching windows.
- **US2:** As a reviewer, I want uncertain fields and validation problems highlighted, with a way to jump between them, so that I check the right things quickly.
- **US3:** As a reviewer, I want to fix fields, including adding or removing line items, and approve the document, so that its data is ready for export.
- **US4:** As the operator, I want every correction recorded, so that I can measure how often documents are approved without edits and grow the eval set (overview §11).

## Acceptance criteria

### Reviewing

- **AC1:** WHEN a member opens the review page of a document in `NEEDS_REVIEW` (or `APPROVED`, read-only), THEN they see:
  - the original file (PDF or image) on one side;
  - on the other, an editable form generated from the document's schema: every field with its label, scalar fields as inputs, line items and taxes as editable tables.
- **AC2:** Fields below the confidence threshold (0.8) and fields named in validation issues are highlighted. A list of open problems is shown, and **Next problem** moves focus to the next highlighted field.
- **AC3:** Edits are checked against the schema as the reviewer types (dates, numbers, GSTIN format), with the message beside the field. An invalid form can't be saved.

### Saving and approving

- **AC4:** WHEN a reviewer saves changes, THEN a new extraction version is stored (`source = human`) with a correction record for each changed field: path, old value, new value, who and when. The document's summary fields (vendor, date, total) update, and validation (F6 checks only, no model calls) runs again on the new version.
- **AC5:** WHEN a reviewer approves, THEN any unsaved valid changes are saved first, the document becomes `APPROVED` with who approved it and when, and the version approved is recorded.
- **AC6:** WHEN two people edit the same document, THEN a save based on an outdated version is rejected with "This document changed since you opened it", and nothing is lost on the server.
- **AC7:** Admins and reviewers can review and approve (F1 Q3). Members of other workspaces get "not found".

### Data for metrics and evals

- **AC8:** The share of documents approved without edits (approved with zero correction records) is available from the data. It is shown on the dashboard as "Approved without edits: N%".
- **AC9:** An operator command exports the operator's own workspace's corrected and approved documents into an eval dataset (files plus truth from the approved version), so corrections grow the eval set. It is never run on other people's workspaces (constitution §5.5).

## Edge cases

- **Approving with open warnings:** allowed, because the reviewer is the judge. Errors need a confirmation ("Approve anyway").
- **A reviewer clears a field:** stored as `null`, which is a valid value for every field (schemas).
- **Very long line-item tables:** the form scrolls within the panel; the document stays visible.
- **The original file can't be shown** (link expired while open): **Reload** gets a fresh 5-minute link.
- **Reopening an approved document:** a non-goal; approved documents are read-only.

## Non-goals

- Drawing boxes on the document to show where a value came from (needs coordinates the model doesn't give).
- Reopening or un-approving documents; deleting documents.
- Assignment queues and multi-step approval.

## Decisions (approved 2026-10-26)

- **D1. Document viewer:** the browser's own PDF viewer (an `<iframe>` of the signed URL) and `<img>` for images. There's no PDF.js bundle: zero dependencies, and it works on phones.
- **D2. The form is generated from the JSON Schema** (labels from `x-ui` where present, else humanised names), so new document types need no new UI. It reuses the F5 field layout.
- **D3. Optimistic concurrency:** saves send the version they were based on; the server rejects a stale base with 409.
- **D4. The eval export** is a CLI (`make eval-import WORKSPACE=<id>`), run by the operator against their own demo workspace only.
