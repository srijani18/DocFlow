# F2: Document upload (tasks)

**Status:** Approved (2026-10-25)
**Prerequisite:** F1 complete. Manual: `SUPABASE_SECRET_KEY` and the `documents-dev` bucket (see the Phase 1 checklist in the PR).

Tests first, named after the criteria; tick each box in the same PR.

- [ ] **F2-T1: Storage client** — `app/storage/` protocol, `SupabaseStorage` (httpx, timeouts) and `FakeStorage`; config `SUPABASE_SECRET_KEY`, `SUPABASE_STORAGE_BUCKET`.
  - **Done when:** `respx` tests cover sign-upload, object-info, sign-view and download, including 404 and 5xx → `StorageUnavailable`.
- [ ] **F2-T2: Tables** — migration `0003_documents` (`uploads`, `documents`), models, tenant meta-test passes.
  - **Done when:** `make migrations-check` passes.
- [ ] **F2-T3: Start upload** (AC1, AC2, AC3, AC10, AC11) — `POST …/uploads`.
  - Tests: `test_ac2_rejects_type_size_and_bad_hash_with_field_errors`, `test_ac3_duplicate_returns_existing_without_ticket`, `test_ac3_same_file_other_workspace_is_new`, `test_ac11_non_member_gets_404`.
- [ ] **F2-T4: Complete upload** (AC1, AC4, AC5, AC11) — object check, document + job in one transaction (job insert via F3's `jobs.service` once F3-T1 lands; until then a stub interface).
  - Tests: `test_ac1_complete_creates_uploaded_document`, `test_ac4_missing_or_wrong_size_object_rejected`, `test_ac5_double_complete_returns_one_document`, `test_ac5_concurrent_identical_uploads_one_document`, `test_ac11_other_workspace_upload_404`.
- [ ] **F2-T5: List, detail and file URL** (AC8, AC9, AC11).
  - Tests: `test_ac8_list_newest_first_paginates_with_cursor`, `test_ac9_file_url_signed_for_5_minutes`, `test_ac11_member_of_a_cannot_list_or_view_b`.
  - **Done when:** `openapi.json` and the TS client are regenerated (`make check-gen` clean).
- [ ] **F2-T6: Web upload** (AC2, AC3, AC6, AC7) — `lib/sha256.ts`, `lib/upload.ts`, `upload-dropzone.tsx`.
  - Tests: `AC2: rejects large or wrong-type files before upload`, `AC3: duplicate shows link to existing document`, `AC6: one failing file doesn't stop the others`, `AC7: shows the synthetic-data notice`.
- [ ] **F2-T7: Web list and detail pages** (AC8, AC9) — `/app/documents`, `/app/documents/[id]`, link from home.
  - Tests: `AC8: list renders and loads more`, `AC9: view original opens a signed URL`.
- [ ] **F2-T8: Local check and close-out** — real upload to `documents-dev` through the UI; spec/plan updated with anything learned; status `Implemented`.
