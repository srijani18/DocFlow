# ADR-0008: Bring your own AI keys, encrypted per workspace

**Status:** Accepted (2026-10-26)

## Context

Phase 1 used one platform Gemini key from the server environment. The owner wants each user (workspace) to bring their own AI keys, so usage, quota and the provider's data terms belong to them. Keys are credentials for someone else's account, so storing them is the most sensitive thing DocFlow does.

## Decision

1. Keys belong to a **workspace** and are managed by its **admins**.
2. Keys are **encrypted at rest** with AES-256-GCM (`cryptography`):
   - with a random 12-byte nonce per encryption;
   - with the workspace id as associated data, so a ciphertext copied to another workspace's row fails to decrypt;
   - under a versioned **master key** held only in the server environment (`BYOK_MASTER_KEYS`), never in the database or the repo.
3. Keys are checked before storing (a list-models call), shown afterwards only as their last 4 characters, never returned by the API, and never logged.
4. The LLM gateway receives keys **per request**, decrypted only for the duration of that call. Providers no longer hold keys.
5. There is **no platform fallback key** in the app. The operator's own keys are used only by the eval CLI and CI (F11).

## Alternatives considered

- **Supabase Vault / pgsodium:** encrypts inside the database. It would tie key handling to Supabase internals that the local Docker Postgres and CI don't have, and the decryption key would sit with the database. Application-level encryption works everywhere and keeps the master key away from the data.
- **A cloud KMS:** the right answer at scale, but there's no free tier without a card. The versioned master-key design leaves room to swap in a KMS-wrapped data key later.
- **Keys in the browser only** (calls made client-side): this would expose keys to page scripts and break background processing, because the worker runs without the user present.

## Consequences

- A database leak alone doesn't reveal keys; the master key must be protected and backed up (losing it means admins re-enter keys, a recoverable inconvenience).
- Circuit breaking and caching become per workspace (quotas are per key).
- Cost figures in `llm_calls` now describe the customer's own spend, which F13 can show back to them.
