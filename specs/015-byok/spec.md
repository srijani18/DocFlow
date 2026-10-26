# F15: Bring your own AI keys (spec)

**Status:** Approved (2026-10-26)
**Phase:** 2 (built before F10, which routes across the keys this adds)
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md) · **ADR:** [0008](../000-architecture/adr/0008-byok-encrypted-keys.md)

## Summary

DocFlow stops using one platform-wide AI key. Each workspace connects its own Gemini, Groq and/or OpenRouter API keys, and all AI processing for that workspace's documents runs on those keys, inside their quota and under their provider account. Keys are encrypted at rest, never shown again after saving (only the last 4 characters), and never logged. Only admins can manage them. File storage, sign-in and the database stay platform-owned.

## User stories

- **US1:** As a workspace admin, I want to connect my own AI provider keys, so that processing uses my account, my quota and my provider's data terms.
- **US2:** As a workspace admin, I want a key checked when I save it, so that a typo shows up straight away rather than as failed documents later.
- **US3:** As a member, I want to know when documents can't be processed because no key is connected, and for them to continue on their own once one is, so that nothing is lost.
- **US4:** As the operator, I want stored keys to be useless to anyone who gets a copy of the database, so that a leak doesn't expose customers' accounts.

## Acceptance criteria

### Managing keys

- **AC1:** WHEN an admin saves a key for a provider (Gemini, Groq or OpenRouter), THEN it is first checked with the provider. A valid key is stored and the provider shows as **Connected** with the key's last 4 characters and the check time. An invalid key is rejected with a clear message and nothing is stored.
- **AC2:** WHEN an admin replaces or removes a key, THEN the change applies to the next AI call; removing deletes the stored key.
- **AC3:** Reviewers see which providers are connected (provider, last 4 characters, check time) but can't add, replace, remove or test keys (F1 Q3: admins manage settings).
- **AC4:** A saved key is never returned by any endpoint, shown in the UI, written to logs or error messages, or sent anywhere except to its own provider.
- **AC5:** WHEN an admin clicks **Test**, THEN the stored key is checked again and its status and check time are updated.

### Using keys

- **AC6:** Every AI call for a document uses only that document's workspace keys. A workspace never uses another workspace's key or a platform key.
- **AC7:** WHEN a document is processed and the workspace has no key for any provider in the task's route, THEN the document becomes `FAILED` straight away (no retries) with the reason "No AI provider key connected", and the UI links admins to the settings page.
- **AC8:** WHEN an admin connects a key, THEN every document that failed only because no key was connected is queued again automatically.
- **AC9:** WHEN a provider rejects a stored key (revoked, expired, wrong project), THEN the provider is marked **Key rejected**, the call falls back to the next provider if there is one (F10), and admins see the status on the settings page.

### Protection

- **AC10:** Keys are stored encrypted with a server-held master key that isn't in the database. A database dump without that master key reveals no key.

## Edge cases

- **Two admins save keys at the same time:** the last save wins; both responses show the final state.
- **The master key is rotated:** keys encrypted under the old version still decrypt (each row records its key version) and are re-encrypted on the next save.
- **A key works but has no quota left:** the provider answers 429; that's a temporary error with fallback (F10), not "Key rejected".
- **The workspace is deleted:** its keys are deleted with it (cascade).
- **Uploading without a key:** allowed; processing waits as in AC7 and AC8.

## Non-goals

- Per-user keys (keys belong to the workspace, shared by its members).
- Platform-paid usage or billing.
- BYOK for storage or sign-in.
- Usage dashboards per key (F13 shows cost and usage from `llm_calls`).

## Decisions (approved 2026-10-26)

- **D1. Keys are per workspace, managed by admins.** Matches F1's roles; a team shares one account.
- **D2. Encryption:** AES-256-GCM from the `cryptography` package (already a dependency), with a 32-byte master key in `BYOK_MASTER_KEYS` (versioned, for rotation) on the server only, and the workspace id as associated data so a ciphertext can't be moved to another workspace. See ADR-0008.
- **D3. Key checks:** a cheap authenticated "list models" call per provider; no document data is sent.
- **D4. No platform key in the app.** `GEMINI_API_KEY` leaves the app's settings. It stays only for the eval CLI and CI (F11), run by the operator with the operator's keys.
- **D5. Missing key is a permanent failure with a code** (`no_ai_key`), so no retry quota is wasted, and AC8 can find and requeue exactly those documents.
