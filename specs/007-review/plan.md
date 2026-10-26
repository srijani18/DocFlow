# F7: Human review (plan)

**Status:** Draft (2026-10-26)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/documents/{document_id}/extraction:
    put:                                   # save corrections (AC4, AC6)
      operationId: saveCorrections
      requestBody: { base_version: int, data: object }    # the whole corrected instance
      responses: { "200": Extraction, "404": {}, "409": {}, "422": {} }   # 409 type version-conflict
  /v1/workspaces/{workspace_id}/documents/{document_id}/approve:
    post:                                  # AC5
      operationId: approveDocument
      requestBody: { version: int, data: object | null, accept_errors: bool }
      responses: { "200": Document, "404": {}, "409": {}, "422": {} }
  /v1/workspaces/{workspace_id}/metrics/review:
    get:                                   # AC8
      operationId: getReviewMetrics
      responses: { "200": { approved: int, approved_without_edits: int, rate: number } }
```

The server computes the per-field diff between the base version and the submitted data (dotted paths, as everywhere). The client never sends correction rows.

## 2. Data model (migration `0010_corrections`)

```sql
CREATE TABLE corrections (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id   uuid NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,  -- the new human version
  path            text NOT NULL,
  old_value       jsonb NULL,
  new_value       jsonb NULL,
  user_id         uuid NOT NULL REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_corrections_workspace_id ON corrections (workspace_id);
CREATE INDEX ix_corrections_document ON corrections (document_id);
ALTER TABLE documents ADD COLUMN approved_extraction_id uuid NULL REFERENCES extractions(id);
```

## 3. Web

```
app/app/documents/[id]/review/page.tsx      split view; viewer left (sticky), form right
components/review/document-viewer.tsx         iframe (PDF) / img, Reload link
components/review/schema-form.tsx             recursive form from the bundled schema (fetched as JSON from
                                              GET /v1/schemas/{schema_id}); tables for arrays of objects
components/review/problem-list.tsx            low-confidence + issues, Next problem (keyboard: J/K)
lib/review/diff.ts, validate.ts               client-side checks matching the schema (date, number, GSTIN pattern)
```

A small public, read-only endpoint, `GET /v1/schemas/{schema_id}`, serves bundled schemas to the form. They are the same files as `schemas/`, contain no tenant data, and need authentication like everything else.

## 4. Flow

```mermaid
sequenceDiagram
  participant R as Reviewer
  participant W as Web
  participant A as API
  R->>W: open review (document NEEDS_REVIEW)
  W->>A: GET document, extraction (version n), issues, schema, file-url
  R->>W: edit fields (validated live)
  R->>W: Approve
  W->>A: POST approve {version: n, data}
  A->>A: diff(n, data) → corrections; insert version n+1 (human); rerun checks
  A->>A: status APPROVED, approved_extraction_id = n+1
  A-->>W: Document (APPROVED)
```

## 5. Security

- Endpoints are workspace-scoped; members only (AC7); reviewers and admins can both approve.
- Submitted data is validated against the schema server-side before anything is stored; the client's checks are a convenience.
- The eval export reads only the workspace id given on the command line, run by the operator against their own data.

## 6. Testing

- **Unit:** diff by path (scalars, nested, line items added or removed); client validation helpers; form rendering from the schema.
- **Integration:**
  - save creates a version and corrections;
  - stale version → 409;
  - approve with and without edits;
  - approving with errors needs `accept_errors`;
  - read-only after approval;
  - cross-workspace 404;
  - metrics;
  - checks re-run on the human version.
- **Web:**
  - the form renders, edits and validates;
  - the problems list and Next problem;
  - approve flow;
  - conflict message;
  - viewer for PDF and image.
- **E2E (local):** review the sample invoice with a deliberate error, fix it, approve, and see the dashboard metric.
