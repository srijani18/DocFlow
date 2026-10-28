# F9: Export (plan)

**Status:** Implemented (2026-10-27)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/export:
    get:
      operationId: exportDocuments
      parameters: format (csv|json), include_unapproved (bool, default false), plus the F8 filters and q
      responses:
        "200": application/zip (csv) or application/json, with Content-Disposition: attachment;
               filename="docflow-export-<yyyymmdd-hhmm>.<zip|json>"
        "404": {}            # not a member
        "422": {}            # more than 5,000 documents: "Narrow the filters"
```

The browser downloads with the user's Bearer token through `fetch` and then saves the blob, because a plain link can't carry the token.

## 2. Columns

`documents.csv`: `document_id, file_name, doc_type, number, document_date, due_date, vendor_name, vendor_gstin, buyer_name, buyer_gstin, currency, subtotal, cgst, sgst, igst, other_tax, tax_total, total, status, approved_at, approved_by, corrections`

- **`number`** is the invoice, receipt or PO number.
- **`due_date`** is the delivery date for purchase orders.
- **Taxes:** `tax_total` is the sum of all tax lines (receipts: their `tax_total`).

`line_items.csv`: `document_id, document_number, line, description, hsn_sac, quantity, unit_price, amount`

## 3. Components

```
app/export/  service.py (select rows via F8's filter builder, map rows), csv_writer.py (escaping, BOM), routes.py
web          Documents page: "Export" menu (CSV / JSON, include not-approved), uses the active search filters
```

The documents are selected in pages of 500 (keyset on `created_at, id`), and each page is written straight into the response stream. CSV rows go into an in-memory ZIP stream (`zipfile` in streaming mode), so the API never holds the whole export.

## 4. Testing

- **Unit:**
  - row mapping per document type;
  - tax column sums;
  - CSV injection escaping;
  - BOM and decimals;
  - the JSON keeps exact amounts.
- **Integration:**
  - approved only by default, plus the include option;
  - filters;
  - the approved version is exported, not a newer one;
  - the limit returns 422;
  - workspace isolation;
  - an empty export has headers only.
- **Web:** the export menu calls the endpoint with the active filters and saves the file.
- **Live:** export the live-check documents and open `documents.csv` (Phase 4 "done when").
