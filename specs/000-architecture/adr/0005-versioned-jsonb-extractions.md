# ADR-0005: Store extractions as versioned JSONB, validated against JSON Schema

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

Each document type (invoice, receipt, purchase order) has a different and evolving shape, with nested line items. An extraction is produced by the model, may be repaired by the validation agent, and may be corrected by a reviewer. We need the full history:

- to show what changed,
- to compute "approved without edits",
- to feed corrections into the eval set,
- to compare prompt and model versions.

## Decision

1. Table `extractions`:
   - `id`, `workspace_id`, `document_id`, `version` (1, 2, …)
   - `source`: `model`, `agent_fix` or `human`
   - `schema_id`, for example `docflow/invoice/v1`
   - `data` (JSONB) and `confidence` (JSONB)
   - `prompt_version`, `llm_call_id`, `created_by`, `created_at`
   - `UNIQUE (document_id, version)`
2. **Rows are append-only.** A correction inserts a new version; nothing is updated in place. The document points at its current version.
3. **Writes are validated** against the JSON Schema named by `schema_id` (from `schemas/`) before insert. Invalid data is rejected or recorded as a failed attempt, never stored as a valid extraction.
4. Fields we filter on (vendor, document date, total, currency) are copied into typed, indexed columns on `documents` when a version becomes current, for search (F8) and summaries (F12).

## Consequences

**Good:**
- Adding a document type or a schema version needs no table migration. Schemas evolve in `schemas/`, each as its own versioned file.
- Full history and provenance: we can show diffs between versions, give exact "approved without edits" counts, and export corrections to evals straight from the rows.
- Schema validation keeps JSONB from turning into an unvalidated dump of whatever the model returned.

**Bad:**
- Querying inside JSONB is less ergonomic and slower than typed columns. That's why the filterable fields are copied out (Decision 4).
- Old versions use storage, out of a 0.5 GB budget. The rows are small (a few KB), so this is fine at portfolio volume, and we can prune versions that are not `model` or the current one if needed.
- Two kinds of schema to keep straight: JSON Schema for document data, and Alembic migrations for tables. `schemas/README.md` documents the boundary.

## Alternatives considered

- **Normalized tables per document type** (`invoices`, `invoice_line_items`, …): strong typing, but every schema change needs a migration, the types multiply, and history needs separate audit tables.
- **A single mutable JSONB column:** simpler, but it loses history, provenance and the "approved without edits" metric.
