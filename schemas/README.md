# `schemas/`: document shapes (single source of truth)

**Status:** Approved (2026-10-24). Schema files added in F5 (2026-10-25): `classification.v1`, `extraction-envelope.v1`, the three document types and `common/`.

These JSON Schemas define the structured data DocFlow extracts from each document type. They are the only place those shapes are defined. Everything else is generated from them or reads them:

| Consumer | Uses the schema for |
|---|---|
| LLM gateway (F10) | The structured-output response schema sent to the provider, after adaptation (see convention 2) |
| Backend | Validating every extraction before it is stored; generated Pydantic models in `apps/api/app/generated/` |
| Frontend | Generated TypeScript types in `apps/web/src/generated/`; the review form fields (F7) |
| Evals (F11) | The format of ground-truth labels and the per-field scoring rules (`x-eval`) |

## Layout

```
schemas/
├─ README.md
├─ common/
│  ├─ money.json              # { amount, currency }
│  ├─ party.json              # vendor/buyer: name, gstin, address
│  └─ address.json
├─ documents/
│  ├─ invoice.v1.json
│  ├─ receipt.v1.json
│  └─ purchase_order.v1.json
└─ classification.v1.json     # classifier output: { doc_type, confidence }
```

## Conventions

### 1. JSON Schema draft 2020-12, with stable IDs

- Every file declares `"$schema": "https://json-schema.org/draft/2020-12/schema"`.
- **Schema ID:** each document schema has a short, stable ID such as `docflow/invoice/v1`. This is the `schema_id` stored on every extraction row (ADR-0005).
- **`$id`:** use an absolute URI that mirrors the file path, for example `"$id": "https://schemas.docflow.dev/documents/invoice.v1.json"`, with the short schema ID kept in a `"x-schema-id": "docflow/invoice/v1"` key.
  - *Why:* JSON Schema resolves a relative `$ref` against the `$id`. With `"$id": "docflow/invoice/v1"`, a reference like `"../common/money.json"` resolves to a path that doesn't match the file layout, and code generators can resolve it differently from validators.
  - An absolute `$id` that mirrors the folders makes file-based tools and ID-based tools agree.
  - The URI is an identifier only and is never fetched.
- Cross-file references use relative paths: `{"$ref": "../common/money.json"}`.

### 2. `x-` keys are for our own tools only

- **`x-eval`:** how a field is scored in evals.
  - `exact`: equal after normalising (trimming and Unicode NFC).
  - `fuzzy`: a normalised string-similarity threshold, set in the eval config.
  - `numeric:<tolerance>`, for example `numeric:0.01`: the absolute difference is at most the tolerance.
- **`x-ui`:** optional hints for the review form, for example `{ "widget": "textarea", "order": 3, "label": "GSTIN" }`.
- **`x-schema-id`:** see convention 1.
- **Before a schema is sent to an LLM**, the gateway's schema adapter:
  - inlines every `$ref` (bundling the schema into one document),
  - removes all `x-*` keys and annotation-only keywords (`$comment`, `examples`), and
  - removes or rewrites keywords the target provider doesn't support, using a support table per provider kept in `app/llm/`.

  The adapter is unit tested against each provider's supported subset.

### 3. Confidence lives outside the schema

The model returns an envelope (`extraction-envelope.v1.json`) that the gateway validates:

```json
{
  "data": { "...": "an instance of the document schema" },
  "confidence": [{ "field": "<field path>", "score": 0.0 }]
}
```

The confidence is a **list** on the wire, because providers' structured output handles arrays of objects more reliably than free-form maps. It is **stored** as the map `{ "<field path>": score }` on the extraction row.

- `data` is validated against the document schema. Each confidence entry needs a `score` from 0 to 1, and its `field` must point at a field that exists in `data`; otherwise the answer is invalid.
- **Field paths:** dotted paths with zero-based indices, for example `vendor.name`, `total.amount` or `line_items.2.quantity`. The same paths are used for review highlighting (F7), `corrections` rows and per-field eval scores.

### 4. Versioning

- **A released schema never changes in a breaking way.** Breaking means: removing or renaming a field, tightening a type or pattern, or making a field required.
- Breaking changes go in a new file (`invoice.v2.json`, ID `docflow/invoice/v2`). v1 stays, so old extractions remain valid against the schema they were stored with.
- Non-breaking additions to a released schema, such as a new optional field, still need a PR that regenerates code and re-runs evals.

### 5. GSTIN

The format is checked in the schema with:

```json
{ "type": "string", "pattern": "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$" }
```

The **checksum** (the 15th character) is checked by the validation agent's tool (F6), not by the schema.

### 6. Shape rules

These make structured outputs more reliable across providers and make eval scoring clearer:

- **Every property is listed in `required`; a value that is missing from the document is `null`** (`"type": ["string", "null"]`). The model must say "not present" explicitly instead of leaving the field out, which separates "not extracted" from "absent" when scoring.
- `"additionalProperties": false` on every object.
- Names are `snake_case`. Dates use `"format": "date"` (ISO 8601 `YYYY-MM-DD`). Currencies are ISO 4217 codes (`INR`).
- `money.amount` is a JSON **number**, which is easier for LLMs than a decimal string. The backend converts it to `Decimal` straight away, and currency arithmetic never uses floats.

### 7. Generated code is never edited by hand

| Output | Tool | Destination |
|---|---|---|
| Pydantic v2 models | `datamodel-code-generator` | `apps/api/app/generated/` |
| TypeScript types | `json-schema-to-typescript` | `apps/web/src/generated/` |

To regenerate everything (schemas plus the OpenAPI client):

```bash
make gen          # regenerate
make check-gen    # regenerate, then fail if git diff shows changes (CI runs this)
```

The exact generator flags live in the `Makefile`, so CI and local runs are identical. Generated files carry a "do not edit" header and are marked `linguist-generated` in `.gitattributes`.

### 8. What does *not* belong here

- **Database tables:** those are Alembic migrations in `apps/api/migrations/`.
- **API request and response models:** those are Pydantic models in the backend. FastAPI generates `openapi.json` from them, and the frontend client is generated from that.
- **Prompts:** those are versioned files in `apps/api/app/llm/prompts/`.
