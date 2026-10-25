# F2: Document upload (spec)

**Status:** Approved (2026-10-25)
**Phase:** 1
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

Members of a workspace upload invoices, receipts and purchase orders as PDF, PNG or JPEG files. The browser sends each file straight to file storage, never through our server, and DocFlow records it as a document in that workspace. Uploading the same file twice doesn't create a second document. Members can see their workspace's documents in a list and open each one, including the original file.

## User stories

- **US1:** As a member, I want to drag and drop one or more documents, so that they are processed without manual typing.
- **US2:** As a member, I want a clear error when a file is too large or of the wrong type, so that I know what to fix.
- **US3:** As a member, I want re-uploading a file I already uploaded to point me to the existing document, so that nothing is processed or counted twice.
- **US4:** As a member, I want to see all documents in my workspace and open one to view the original file, so that I can check what was uploaded.
- **US5:** As the operator, I want files to be readable and writable only through access the backend grants for the caller's own workspace, so that no workspace can see another's files.

## Acceptance criteria

### Uploading

- **AC1:** WHEN a member uploads a PDF, PNG or JPEG of at most 10 MB, THEN the file is stored, a document with status `UPLOADED` appears in the workspace's document list, and processing is queued (F3).
- **AC2:** WHEN a file is larger than 10 MB, empty, or of any other type, THEN it is rejected before any bytes are stored, with a message naming the limit or the allowed types. The server enforces the same rules even if the browser's checks are bypassed.
- **AC3:** WHEN a file with the same content (SHA-256) already exists as a document in the workspace, THEN no new document or processing job is created, and the user is shown the existing document. The same file in a *different* workspace is a separate document.
- **AC4:** WHEN the browser reports an upload as finished, THEN the server confirms the file is actually in storage with the declared size before creating the document. If it isn't, the request is rejected and no document is created.
- **AC5:** WHEN the same upload is reported finished more than once (a retry or double click), THEN exactly one document exists and every response returns it.
- **AC6:** WHEN several files are dropped at once, THEN each is uploaded and reported independently, with its own progress and result. One file failing doesn't stop the others.
- **AC7:** The upload area always tells the user to upload only sample or synthetic documents, because they are sent to free AI services that may keep them (constitution §5.5).

### Viewing

- **AC8:** WHEN a member opens the document list, THEN they see their workspace's documents, newest first, with file name, size, status and upload time, 50 at a time with a way to load more.
- **AC9:** WHEN a member opens a document, THEN they see its details, and they can view the original file through a link that stops working after 5 minutes.

### Access

- **AC10:** Admins and reviewers can both upload and view (F1 Q3).
- **AC11:** WHEN a user tries to start, finish or view an upload or document in a workspace they don't belong to, or names another workspace's upload, THEN the response is "not found", and no file access is granted. A user can never read or write another workspace's storage location.

## Edge cases

- **Two identical files dropped at the same moment:** one document is created; the other upload resolves to it (AC3, AC5).
- **Upload started but never finished** (tab closed): no document exists. The unfinished upload expires after 2 hours. Removing its orphaned file from storage is deferred to F14.
- **File renamed but identical content:** it's a duplicate (AC3). The original document keeps its first name.
- **A file whose extension doesn't match its content** (e.g. a `.pdf` that is really a ZIP): accepted by type and size here; the pipeline fails it as unreadable (F3).
- **Storage temporarily unavailable:** the upload fails with a "try again" message; nothing is recorded.
- **Very slow upload:** the upload permission lasts 2 hours, which covers 10 MB on any working connection.

## Non-goals

- Multi-page TIFF, HEIC, Word or Excel files; email or API ingestion.
- Deleting or renaming documents (later feature).
- Resumable uploads, and files over 10 MB.
- Cleaning up storage files from abandoned uploads (F14).
- Virus scanning.

## Decisions (approved 2026-10-25)

- **D1. Size and types:** 10 MB; PDF, PNG and JPEG, matching the brief and ADR-0004. Enforced in the browser, in the API and by the bucket.
- **D2. Duplicate scope:** per workspace, by SHA-256 of the file bytes, computed in the browser. The pipeline re-checks the hash after download (F3 AC7), so a lying client gains nothing.
- **D3. Unfinished uploads** expire after 2 hours, matching the lifetime of a Supabase signed upload URL.
- **D4. View link lifetime:** 5 minutes.
