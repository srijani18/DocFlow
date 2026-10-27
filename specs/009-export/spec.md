# F9: Export (spec)

**Status:** Implemented (2026-10-27)
**Phase:** 4
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

Approved data is the product. Members export it to take into a spreadsheet or an accounting tool:

- **CSV:** one file of documents and one of line items, zipped together.
- **JSON:** every approved document's full data with its metadata.

An export takes the same filters as search (F8), so "everything from Kaveri approved in August" is one click.

## User stories

- **US1:** As a member, I want to download approved documents as CSV, so that I can open them in Excel or import them into accounting software.
- **US2:** As a member, I want line items in their own file, linked to their document, so that item-level analysis works.
- **US3:** As a developer integrating DocFlow, I want a JSON export with exact amounts and the full data, so that nothing is lost.

## Acceptance criteria

- **AC1:** WHEN a member exports, THEN they get the workspace's **approved** documents matching the current filters (F8 AC4), newest first. Documents in other statuses are only included when the member ticks "Include documents not yet approved", and then each row says its status.
- **AC2:** **CSV** is a ZIP with two files:
  - `documents.csv`: one row per document. Columns: id, file name, type, number, document date, due date, vendor name and GSTIN, buyer name and GSTIN, currency, subtotal, CGST, SGST, IGST, other taxes, tax total, total, status, approved at, approved by (a person's email, or "agent"), and corrections.
  - `line_items.csv`: one row per line item. Columns: document id, document number, line number, description, HSN/SAC, quantity, unit price, amount.

  Column names are stable and documented in the plan.
- **AC3:** **JSON** is one array of `{document: {…metadata}, data: {…approved version}}`. Amounts are exact decimal numbers, exactly as stored (F5 AC8).
- **AC4:** Amounts in CSV are plain decimals with a dot (`16826.80`). Dates are ISO (`2026-08-14`). Files are UTF-8 with a byte-order mark, so Excel shows ₹ and non-English names correctly.
- **AC5:** A CSV cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is prefixed with `'`. A spreadsheet then never runs a formula from document content (CSV injection).
- **AC6:** Exports are limited to 5,000 documents. Above that, the member is asked to narrow the filters. The response streams, so memory use stays flat.
- **AC7:** Exports are workspace-scoped. Any member (admin or reviewer) can export. Members of other workspaces get "not found".
- **AC8:** The data exported for a document is its **approved** version (`approved_extraction_id`). For documents not yet approved (AC1 option), it's the current version, and the row says so.

## Edge cases

- **No matching documents:** a valid empty file (headers only), not an error.
- **A field missing from a document type** (receipts have no buyer): an empty cell.
- **Several taxes of the same kind:** summed per column. The JSON keeps every tax line.
- **A document type added later:** JSON needs no change. CSV maps it through the same summary fields.

## Non-goals

- Direct pushes to Tally, Zoho or QuickBooks.
- Scheduled or emailed exports.
- Excel `.xlsx` files: CSV opens in Excel, and stays dependency-free.

## Decisions (approved 2026-10-27)

- **D1. Formats:** CSV (zipped pair) and JSON. A single flat CSV with repeated document columns per line item was considered: it is easier for some imports, but duplicates totals and confuses sums.
- **D2. Synchronous streaming download**, not a background job with a link. 5,000 documents is a few MB, and a job would need storage, expiry and cleanup for no benefit at this size.
- **D3. Approved data only by default (AC1):** export is for data a person (or the agent) has vouched for.
