# F2: Document upload (plan)

**Status:** Draft (2026-10-25)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Approach

Direct-to-storage upload with signed URLs (ADR-0004), in three calls:

1. **Start:** the browser hashes the file (Web Crypto SHA-256) and sends name, type, size and hash. The API checks the caller's membership, the type and size, and duplicates. If it's new, it records an `uploads` row and returns a Supabase **signed upload token** for `{workspace_id}/{upload_id}`.
2. **Upload:** the browser PUTs the bytes to Supabase Storage with `supabase.storage.from(bucket).uploadToSignedUrl(path, token, file)`.
3. **Complete:** the browser calls the API. The API reads the object's metadata from Storage (secret key), checks that the size matches, and in **one transaction** inserts the document and its processing job (F3).

The storage path is always built by the server from the upload row, so a client can't name another workspace's path.

## 2. API contract (OpenAPI fragment)

```yaml
paths:
  /v1/workspaces/{workspace_id}/uploads:
    post:
      operationId: startUpload
      requestBody: { content: { application/json: { schema: { $ref: "#/components/schemas/UploadStart" } } } }
      responses:
        "201": { description: New upload; put the bytes, then complete, content: { application/json: { schema: { $ref: "#/components/schemas/UploadTicket" } } } }
        "200": { description: Duplicate; nothing to upload, content: { application/json: { schema: { $ref: "#/components/schemas/UploadDuplicate" } } } }
        "401": {} "404": {} "422": {}   # 422 field errors for type/size/hash (AC2)
  /v1/workspaces/{workspace_id}/uploads/{upload_id}/complete:
    post:
      operationId: completeUpload
      responses:
        "201": { content: { application/json: { schema: { $ref: "#/components/schemas/Document" } } } }
        "200": { description: Already completed, or the same content was completed by another upload, content: { application/json: { schema: { $ref: "#/components/schemas/Document" } } } }
        "404": {}   # unknown, expired, or another workspace's upload (AC11)
        "409": {}   # type upload-incomplete: object missing or size differs (AC4)
  /v1/workspaces/{workspace_id}/documents:
    get:
      operationId: listDocuments
      parameters: [ { name: cursor, in: query }, { name: limit, in: query, schema: { default: 50, maximum: 100 } } ]
      responses: { "200": { content: { application/json: { schema: { $ref: "#/components/schemas/DocumentPage" } } } } }
  /v1/workspaces/{workspace_id}/documents/{document_id}:
    get: { operationId: getDocument, responses: { "200": { $ref: Document }, "404": {} } }
  /v1/workspaces/{workspace_id}/documents/{document_id}/file-url:
    post: { operationId: createDocumentFileUrl, responses: { "200": { $ref: FileUrl }, "404": {} } }   # POST: it mints a credential
components:
  schemas:
    UploadStart:  { filename: string(1..255), content_type: enum[application/pdf, image/png, image/jpeg], size_bytes: int(1..10485760), sha256: string(^[0-9a-f]{64}$) }
    UploadTicket: { kind: "upload", upload_id: uuid, bucket: string, path: string, token: string, expires_at: date-time }
    UploadDuplicate: { kind: "duplicate", document: Document }
    Document:     { id, filename, content_type, size_bytes, sha256, status, failure_reason: string|null, created_at, updated_at }   # F3–F5 add fields
    DocumentPage: { items: Document[], next_cursor: string|null }
    FileUrl:      { url: uri, expires_at: date-time }
```

`next_cursor` is an opaque base64 of `(created_at, id)`; ordering is `created_at DESC, id DESC`, so pages are stable while new documents arrive.

## 3. Data model (migration `0003_documents`)

```sql
CREATE TABLE uploads (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  created_by_user_id  uuid NOT NULL REFERENCES users(id),
  filename            text NOT NULL,
  content_type        text NOT NULL,
  size_bytes          integer NOT NULL,
  sha256              text NOT NULL,
  expires_at          timestamptz NOT NULL,
  document_id         uuid NULL,             -- set when completed (AC5)
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_uploads_workspace_id ON uploads (workspace_id);

CREATE TABLE documents (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  upload_id           uuid NOT NULL UNIQUE REFERENCES uploads(id),
  storage_path        text NOT NULL,         -- {workspace_id}/{upload_id}
  filename            text NOT NULL,
  content_type        text NOT NULL CHECK (content_type IN ('application/pdf','image/png','image/jpeg')),
  size_bytes          integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
  sha256              text NOT NULL,
  status              text NOT NULL,         -- values and CHECK owned by F3
  failure_reason      text NULL,
  created_by_user_id  uuid NOT NULL REFERENCES users(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_documents_workspace_sha256 UNIQUE (workspace_id, sha256)
);
CREATE INDEX ix_documents_workspace_created ON documents (workspace_id, created_at DESC, id DESC);
```

- `uq_documents_workspace_sha256` is the real duplicate guard (AC3). The check at **start** is only a shortcut; a race between two identical uploads is settled at **complete** by `INSERT … ON CONFLICT (workspace_id, sha256) DO NOTHING`, returning the existing document.
- Both tables carry an indexed `workspace_id`, so the tenant meta-test covers them.

## 4. Components

```
app/storage/   client.py   StorageClient protocol: create_signed_upload(path) · object_info(path) · create_signed_url(path, ttl) · download(path)
               supabase.py SupabaseStorage (httpx, secret key, 10 s timeout; download 30 s)
               fake.py     FakeStorage for tests (in-memory objects)
app/documents/ models.py · schemas.py · repository.py · service.py · routes.py
web: app/app/documents/page.tsx (list + dropzone) · app/app/documents/[id]/page.tsx (detail)
     components/upload-dropzone.tsx · lib/upload.ts (hash → start → upload → complete) · lib/sha256.ts
```

Supabase Storage REST calls used (checked against the Storage API at implementation time):
`POST /storage/v1/object/upload/sign/{bucket}/{path}` (signed upload token), `GET /storage/v1/object/info/{bucket}/{path}` (size and type), `POST /storage/v1/object/sign/{bucket}/{path}` (signed view URL), `GET /storage/v1/object/{bucket}/{path}` (download, used by F3).

## 5. Sequence

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as API
  participant S as Storage
  participant DB as Postgres
  B->>B: sha256(file), check type/size
  B->>A: POST /uploads {name, type, size, sha256}
  A->>DB: document with this sha256 in workspace?
  alt duplicate
    A-->>B: 200 {kind: duplicate, document}
  else new
    A->>DB: INSERT uploads
    A->>S: sign upload for {ws}/{upload_id}
    A-->>B: 201 {kind: upload, path, token}
    B->>S: PUT bytes (signed token)
    B->>A: POST /uploads/{id}/complete
    A->>S: object info → size matches?
    A->>DB: BEGIN; INSERT document ON CONFLICT DO NOTHING; INSERT job; UPDATE uploads SET document_id; COMMIT
    A-)A: wake worker (F3)
    A-->>B: 201 Document
  end
```

## 6. Error handling

| Situation | Status | Problem type |
|---|---|---|
| Type, size or hash format invalid | 422 | `validation` with field errors (AC2) |
| Unknown, expired or other-workspace upload | 404 | `not-found` (AC11) |
| Object missing or size differs at complete | 409 | `upload-incomplete` (AC4) |
| Storage unreachable or 5xx | 503 | `storage-unavailable`, `Retry-After: 5` |

## 7. Security

- Bucket is **private with no policies**; only signed tokens and URLs minted by the API grant access (ADR-0004). The secret key lives only in the API's environment.
- Paths are server-built from `upload_id`; the client never supplies a path (AC11).
- The bucket enforces 10 MB and the MIME allowlist too (manual step), so a modified client can't upload more than the ticket allows.
- View URLs live 5 minutes and are minted per request by a member.
- Filenames are stored as given but only ever rendered as text, and never used in storage paths.

## 8. Risks

| Risk | Mitigation |
|---|---|
| A client lies about the hash to dodge duplicate detection | Harmless to other workspaces; the pipeline re-hashes and fails mismatches (F3 AC7). |
| Supabase Storage API details differ from this plan | The storage client is small and tested with `respx` against recorded responses; checked against the live `documents-dev` bucket during implementation. |
| Orphaned objects from abandoned uploads use storage quota | Bounded by 10 MB each; cleanup is F14. |

## 9. Testing

- **Unit:** `UploadStart` validation; cursor encoding; the Supabase storage client with `respx`.
- **Integration (real Postgres, `FakeStorage`):** each AC as `test_acN_*`, including the concurrent-complete race (AC5) and cross-workspace attempts using the `two_workspaces` fixture (AC11).
- **Web (Vitest):** dropzone validation messages (AC2), duplicate message (AC3), per-file progress (AC6), the notice (AC7), list rendering (AC8).
- **Manual, local:** a real upload against the `documents-dev` bucket.

## 10. Configuration added

`SUPABASE_SECRET_KEY` (secret), `SUPABASE_STORAGE_BUCKET` (`documents-dev` locally, `documents` in production), `UPLOAD_MAX_BYTES` (default 10485760). Web: `NEXT_PUBLIC_*` already present.
