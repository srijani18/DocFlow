# ADR-0004: Upload directly from the browser to storage with signed URLs

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

Uploads are up to 10 MB each. The backend has 512 MB of RAM, 0.1 CPU, an ephemeral disk and 5 GB a month of outbound bandwidth. Proxying file bytes through it would use memory and CPU, block the event loop during slow client uploads, and spend bandwidth when files are viewed.

## Decision

1. The browser asks the API for an upload. The API checks authentication, membership, declared size and type, and duplicates (by SHA-256). It then creates a **signed upload URL** with the Supabase **secret key**, for the path `{workspace_id}/{uuid}`.
2. The browser uploads directly to Supabase Storage with the publishable key and the signed token.
3. The browser confirms completion to the API. The API checks that the object exists and that its size matches, then records the document and queues the job in one transaction.
4. The bucket is **private** and has **no storage access policies**, so the only way in is a URL signed by the backend. The bucket enforces a **10 MB** limit and the allowed types (PDF, PNG, JPEG).
5. Viewing works the same way: the API returns a short-lived **signed download URL**, and bytes never pass through the API.
6. The worker downloads bytes with the secret key, holds them in memory only, and sends them to the LLM.

## Consequences

**Good:**
- The API handles only small JSON requests. Large or slow uploads can't exhaust the instance.
- Storage enforces its limits even if the backend's own checks have a bug (defense in depth).
- Tenant paths plus backend-only signing mean one workspace can't reach another's files (F2, AC4).

**Bad:**
- The SHA-256 is computed by the client, so a buggy or hostile client could lie about it. The worker recomputes the hash from the stored bytes and records it. If it differs, the document is flagged, and duplicate detection uses the server-side hash from then on. Details in F2.
- Uploads that are never confirmed leave orphan objects. A periodic cleanup job deletes objects with no document row after 24 hours (F2).
- There are two network steps instead of one, so the UI must handle partial failure (upload succeeded, confirmation failed). Retrying the confirmation is idempotent, keyed by the path.

## Alternatives considered

- **Multipart upload through FastAPI:** the simplest code, but it uses the instance's scarce resources and bandwidth.
- **Supabase storage access policies tied to the user's JWT:** possible, but tenancy rules would then live in two places (storage policies in Supabase and checks in our API). Keeping all authorization in the backend is easier to reason about and to test.
