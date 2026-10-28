# F9: Export (tasks)

**Status:** Implemented (2026-10-27)
**Prerequisite:** F8 (filters).

- [x] **F9-T1: Row mapping and CSV writer** (AC2, AC4, AC5): per-type mapping, tax sums, escaping, BOM.
- [x] **F9-T2: Export endpoint** (AC1, AC3, AC6–AC8): streaming CSV ZIP and JSON, approved version, limit, isolation.
- [x] **F9-T3: Export UI**: menu on the Documents page with the active filters.
- [x] **F9-T4: Live check and close-out:** export, open in a spreadsheet, check the amounts against the approved versions.
  - **Done (2026-10-27), in a real browser:** Export → CSV saved `docflow-export.zip`.
    - `documents.csv` has the reviewed invoice: total 3424.95 (the corrected value), IGST 522.45, approved by the reviewer's email, 1 correction, with a UTF-8 BOM.
    - `line_items.csv` has its 2 lines.
  - Notes:
    - With search text, the export contains exactly what the search shows (keyword and meaning, at most 200 documents). Without text, it contains everything matching the filters, up to 5,000.
    - Money is written with at least two decimals.
