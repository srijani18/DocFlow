# F5: Structured extraction (plan)

**Status:** Approved (2026-10-25)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Approach

- **Schemas first:** write `schemas/common/*.json` and `schemas/documents/{invoice,receipt,purchase_order}.v1.json` following `schemas/README.md` (draft 2020-12, absolute `$id`, `x-schema-id`, every property required and nullable, `additionalProperties: false`). `make gen-schemas` produces Pydantic models in `apps/api/app/generated/` and TS types in `apps/web/src/generated/`; `make check-gen` guards them.
- **Extract step:** `app/pipeline/steps/extract.py`. Skips if an extraction exists for this document's `processing_generation` (AC5). Otherwise calls `Gateway.generate` with prompt `extract/v1` (a shared template plus a per-type section), the file, and the **envelope schema** `{ data: <doc schema>, confidence: { <path>: number 0..1 } }`. On success, in one transaction: insert extraction version, set `documents.current_extraction_id` and the summary columns (AC7), transition to `NEEDS_REVIEW`.
- **Confidence paths:** dotted paths with zero-based indices (`vendor.gstin`, `line_items.2.amount`), as in `schemas/README.md` §3. The validator checks that every path refers to a field that exists in `data`; unknown paths make the answer invalid (AC3). Missing paths are allowed and shown as "no confidence".

## 2. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/documents/{document_id}/extraction:
    get:
      operationId: getCurrentExtraction
      responses:
        "200": { content: { application/json: { schema: { $ref: Extraction } } } }
        "404": {}   # no such document, other workspace, or no extraction yet
components:
  schemas:
    Extraction: { id: uuid, version: int, source: enum[model, agent_fix, human], schema_id: string, data: object, confidence: { additionalProperties: number }, prompt_version: string|null, created_at: date-time }
    Document: { ..., vendor_name: string|null, document_date: date|null, total_amount: string|null, currency: string|null }   # total as a decimal string (AC8)
```

`data` is typed as a free-form object in OpenAPI; the web app narrows it with the TS types generated from `schemas/`, chosen by `schema_id`.

## 3. Data model (migration `0006_extractions`)

```sql
CREATE TABLE extractions (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id       uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version           integer NOT NULL,
  source            text NOT NULL CHECK (source IN ('model','agent_fix','human')),
  schema_id         text NOT NULL,
  data              jsonb NOT NULL,
  confidence        jsonb NOT NULL DEFAULT '{}',
  prompt_version    text NULL,
  llm_call_id       uuid NULL REFERENCES llm_calls(id) ON DELETE SET NULL,
  processing_generation integer NOT NULL,       -- idempotency per processing run (AC5)
  created_by_user_id uuid NULL REFERENCES users(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_extractions_document_version UNIQUE (document_id, version)
);
CREATE INDEX ix_extractions_workspace_id ON extractions (workspace_id);
CREATE UNIQUE INDEX uq_extractions_model_run ON extractions (document_id, processing_generation) WHERE source = 'model';

ALTER TABLE documents
  ADD COLUMN current_extraction_id uuid NULL REFERENCES extractions(id),
  ADD COLUMN vendor_name   text NULL,
  ADD COLUMN document_date date NULL,
  ADD COLUMN total_amount  numeric(18,2) NULL,
  ADD COLUMN currency      char(3) NULL;
CREATE INDEX ix_documents_workspace_vendor ON documents (workspace_id, vendor_name);
CREATE INDEX ix_documents_workspace_date ON documents (workspace_id, document_date);
```

- **Append-only:** the app's repository has no update or delete for `extractions` (ADR-0005). Version = `max(version)+1` under the document row lock taken by `transition()`.
- **Money (AC8):** the JSON number from the model is parsed with `json.loads(..., parse_float=Decimal)`, so `total_amount` never passes through a float; JSONB keeps the number as written.

## 4. Schema fields (v1)

| Schema | Fields |
|---|---|
| `common/address.json` | `line1, line2, city, state, postal_code, country` (strings, nullable) |
| `common/party.json` | `name, gstin (GSTIN pattern), address (address|null)` |
| `common/money.json` | `amount (number), currency (ISO 4217, ^[A-Z]{3}$)` — both nullable |
| `documents/invoice.v1.json` | `invoice_number, invoice_date, due_date, vendor (party), buyer (party), place_of_supply, line_items[{description, hsn_sac, quantity, unit_price (money), amount (money)}], subtotal (money), taxes[{type: CGST/SGST/IGST/CESS/OTHER, rate_percent, amount (money)}], total (money), currency` |
| `documents/receipt.v1.json` | `receipt_number, date, time, merchant (party), line_items[{description, quantity, amount (money)}], subtotal, tax_total, total (money), payment_method, currency` |
| `documents/purchase_order.v1.json` | `po_number, po_date, delivery_date, buyer (party), vendor (party), line_items[{description, hsn_sac, quantity, unit_price, amount}], subtotal, taxes[…], total (money), currency` |

`x-eval` hints are set per field (numbers `numeric:0.01`, IDs `exact`, names and addresses `fuzzy`) for F11; `x-ui` labels and order for the detail page. Summary columns (AC7) map from `vendor.name|merchant.name`, `invoice_date|date|po_date`, `total.amount`, `total.currency|currency`.

## 5. Components

```
schemas/common/*.json · schemas/documents/*.v1.json · schemas/extraction-envelope.v1.json
app/schemas_registry.py   load + bundle schemas by schema_id; jsonschema validators (cached)
app/llm/prompts/extract/v1.md
app/pipeline/steps/extract.py
app/extractions/          models.py · repository.py (insert_version, get_current) · service.py · routes.py · schemas.py
evals/samples/            generate_synthetic.py (dev-only script) → synthetic-invoice-001.pdf, synthetic-receipt-001.png, …
web: app/app/documents/[id]/extraction-view.tsx (fields, line-item table, confidence highlighting, raw JSON toggle)
     list columns: type, vendor, total
```

## 6. Sequence

```mermaid
sequenceDiagram
  participant W as Worker
  participant G as Gateway
  participant M as Gemini
  participant DB as Postgres
  W->>DB: extraction for this generation exists? → skip
  W->>G: generate(extract/v1, file, envelope(invoice.v1))
  G->>M: generateContent (adapted schema, JSON mode)
  M-->>G: JSON
  G->>G: validate data + confidence paths
  G->>DB: llm_calls row (own transaction)
  G-->>W: data, confidence
  W->>DB: BEGIN; INSERT extraction v1; UPDATE documents summary + current; transition NEEDS_REVIEW; COMMIT
```

## 7. Error handling

| Situation | Effect |
|---|---|
| Invalid data or confidence | `llm_calls.outcome = invalid_output`; transient; after 5 attempts document `FAILED`, "Couldn't extract valid data" |
| Output truncated (finish reason `MAX_TOKENS`) | Treated as invalid output |
| Provider errors | As F4 |
| `doc_type = other` | Step not run (F4 AC3) |

## 8. Security

- Extraction endpoints are workspace-scoped like every document endpoint; `extractions.workspace_id` is always filtered (constitution §4).
- Raw JSON is rendered as text, never as HTML.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Gemini's structured output rejects a schema feature (e.g. `pattern`, nullable unions) | The adapter drops unsupported keywords for the provider; our own validation still enforces them. Covered by adapter tests and the manual check. |
| Large envelope schema hurts accuracy | Measured in Phase 2 (F11) with prompt versions; v1 keeps fields to the table above. |
| Model returns confidences of 1.0 for everything | Shown as-is in Phase 1; calibration is evaluated in F11. |

## 10. Testing

- **Unit:** every schema validates its examples and rejects bad GSTINs, extra fields and missing keys; envelope + confidence-path validation; Decimal parsing; summary-column mapping per type.
- **Integration (FakeProvider):** `test_ac1_*` per type, `test_ac3_invalid_answer_not_stored_and_retried`, `test_ac4_extraction_records_provenance`, `test_ac5_rerun_no_call_no_new_version`, `test_ac7_summary_columns_updated`, cross-workspace 404 on the extraction endpoint.
- **Web:** `AC6: shows fields, line items and highlights low confidence`, `AC6: raw JSON toggle`, `AC7: list shows vendor and total`.
- **Manual (Phase 1 "done when"):** upload `synthetic-invoice-001.pdf` locally and see its extracted fields in the UI.


## 11. Implementation notes (F5-T1 to T6)

- **Confidence on the wire is a list** of `{field, score}` (providers handle arrays of objects better than free-form maps) and is stored as the map `{path: score}`. `schemas/README.md` convention 3 updated.
- **Exact amounts:** answers are parsed with `Decimal`, and extraction JSON is written as exact JSON text cast to JSONB in SQL (`app/extractions/exact_json.py`), so stored numbers keep every digit (test: `test_ac8_amounts_stored_exactly`). `documents.total_amount` is `numeric(18,2)` and the API returns it as a decimal string.
- **Readable validation errors:** for "object or null" fields, the validator reports the closest branch's own problem (`vendor.gstin: … does not match …`) instead of "not valid under any of the given schemas".
- **Codegen:** `make gen-schemas` feeds the generators a JSON-only copy of `schemas/`; TypeScript types are generated per file, because json2ts resolves `$ref`s against its working directory.
- **The web view is schema-agnostic:** it lays out any extraction from its data (scalars as rows, arrays of objects as tables) and highlights fields below 0.8 confidence, so new document types need no UI code.
- **Samples:** `evals/samples/generate_synthetic.py` writes synthetic PDFs plus ground-truth JSON, which the schema tests validate, and which F11 will reuse.


## 12. Phase 1 "done when", checked locally on 2026-10-26

Real services: Supabase Storage (`documents-dev`), Gemini free tier, local API, worker and web app, driven in headless Chromium.

- The three synthetic samples were uploaded together; statuses moved Queued → Classifying → Extracting → Needs review live, without reloads.
- Classification: invoice, receipt and the letter as `other` (which skipped extraction). Each took about 3 s on `gemini-3.5-flash-lite`.
- Extraction: every top-level invoice field matched `evals/samples/synthetic-invoice-001.json`; the list shows the vendor and ₹16,826.80. Extraction took 4–6 s on `gemini-3.5-flash-lite` (962 input tokens; 1,300–2,400 output tokens; estimated $0.0035–0.0063).
  - Source: `SELECT task, model, latency_ms, input_tokens, output_tokens, cost_usd FROM docflow.llm_calls WHERE outcome = 'ok'`.
- Resilience under real failures: the first extraction attempts on `gemini-flash-latest` timed out or returned 503; the jobs retried with backoff and one succeeded on attempt 5 after the model switch (F5 D1). A job interrupted by an API reload was reclaimed when its lease expired.
- Found and fixed during the check:
  - JSONB doesn't keep key order, so the API now returns `data` in schema order.
  - Token counts were redacted from logs by the secret filter.
  - The receipt's ground truth now copies the merchant name as printed.
