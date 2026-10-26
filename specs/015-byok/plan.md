# F15: Bring your own AI keys (plan)

**Status:** Approved (2026-10-26)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/ai-keys:
    get:                       # any member (AC3)
      operationId: listAiKeys
      responses: { "200": { content: { application/json: { schema: { type: array, items: { $ref: AiKeyStatus } } } } } }
  /v1/workspaces/{workspace_id}/ai-keys/{provider}:     # provider: gemini | groq | openrouter
    put:                       # admin; body { api_key }; checked before storing (AC1)
      operationId: saveAiKey
      responses: { "200": { $ref: AiKeyStatus }, "403": {}, "404": {}, "422": {} }   # 422 type invalid-api-key
    delete:                    # admin (AC2)
      operationId: deleteAiKey
      responses: { "204": {}, "403": {}, "404": {} }
  /v1/workspaces/{workspace_id}/ai-keys/{provider}/test:
    post:                      # admin (AC5)
      operationId: testAiKey
      responses: { "200": { $ref: AiKeyStatus }, "403": {}, "404": {} }
components:
  schemas:
    AiKeyStatus:
      { provider: enum[gemini, groq, openrouter], connected: boolean,
        last4: string|null, status: enum[ok, rejected, unchecked]|null,
        checked_at: date-time|null, updated_at: date-time|null }
    AiKeySave: { api_key: string(8..512) }   # never echoed back (AC4)
    Document: { ..., failure_code: string|null }   # e.g. no_ai_key (AC7)
```

`GET` always returns all three providers, with `connected: false` for those without a key, so the UI is simple.

## 2. Data model (migration `0007_ai_keys`)

```sql
CREATE TABLE workspace_ai_keys (
  workspace_id   uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider       text NOT NULL CHECK (provider IN ('gemini','groq','openrouter')),
  ciphertext     bytea NOT NULL,          -- AES-256-GCM output (includes the tag)
  nonce          bytea NOT NULL,          -- 12 random bytes per encryption
  key_version    integer NOT NULL,        -- which master key encrypted it (rotation)
  last4          text NOT NULL,
  status         text NOT NULL CHECK (status IN ('ok','rejected','unchecked')),
  checked_at     timestamptz NULL,
  updated_by_user_id uuid NOT NULL REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_workspace_ai_keys PRIMARY KEY (workspace_id, provider)
);
ALTER TABLE documents ADD COLUMN failure_code text NULL;
```

The table's primary key leads with `workspace_id`, so the tenant meta-test covers it.

## 3. Components

```
app/aikeys/  crypto.py      KeyBox: encrypt(workspace_id, plaintext) → (ciphertext, nonce, version);
                            decrypt(...) with AAD = workspace_id; BYOK_MASTER_KEYS = "v1:<base64 32B>[,v2:…]"
             checks.py      check_key(provider, key, http) → ok | rejected | unavailable (list-models call, 10 s)
             models.py · repository.py · service.py · routes.py · schemas.py
app/llm/     credentials.py WorkspaceCredentials: keys for one workspace, decrypted only for the duration
                            of a call; providers get the key per request, not at construction
```

- **Gateway change:** `GeminiProvider` and the F10 providers take the API key per request (`ProviderRequest.api_key`). `Gateway.generate` loads the workspace's keys (context has `workspace_id`), drops route entries without a key, and if nothing is left raises `NoCredentialsError`. The extract and classify steps map that to `PermanentError(reason="No AI provider key connected", code="no_ai_key")`.
- **Key rejected (AC9):** a 401/403 from a provider while using a stored key raises `CredentialRejectedError`. The gateway marks the key `rejected` in its own transaction, then falls through to the next route entry (F10). With only one provider it's a permanent failure with code `key_rejected`.
- **Auto-requeue (AC8):** in the same transaction as saving a key, `documents.service.retry_failed_with_code(scope, "no_ai_key")` requeues those documents (as F3's retry does), and the worker is woken after commit.
- **Circuit breaker (F10):** keyed by (workspace, provider, model), because quotas are per key.
- **Logging:** the key never enters a log call. `ProviderRequest.api_key` is a `SecretStr`, the redaction processor already masks `api_key`, and a test asserts no key text appears in captured logs.

## 4. Web

- `/app/settings` (sidebar item "Settings"): one card per provider with its logo initial, status pill (Connected …abcd / Key rejected / Not connected), check time, and, for admins, **Add key** / **Replace** / **Remove** / **Test**. Keys go in a password field; after saving, only the masked status remains.
- The dashboard shows a gradient banner, "Connect an AI provider to start processing", when no provider is connected.
- On a FAILED document with `failure_code = no_ai_key`, the problem box links to Settings.

## 5. Configuration

- **Added:** `BYOK_MASTER_KEYS` [secret], format `v1:<base64 of 32 random bytes>`, comma-separated for rotation; the highest version encrypts. `make byok-key` prints a fresh one.
- **Removed from the app:** `GEMINI_API_KEY` (still read by the eval CLI only, F11).
- Local `.env`: a generated dev master key. After this lands, you paste your Gemini key into Settings rather than `.env`.

## 6. Security

- The master key lives only in Render or local `.env`, never in the database or repo. GCM gives integrity; AAD binds a ciphertext to its workspace (AC10).
- Plaintext keys exist only in memory during a check or a call.
- Endpoints are workspace-scoped; mutations use `AdminScopeDep`.
- Responses never contain the key (AC4); a contract test asserts `AiKeyStatus` has no field for it.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Losing the master key makes stored keys unreadable | Keys are user-replaceable: admins re-enter them. Documented in the deploy guide; back it up in a password manager. |
| A provider's "list models" check needs different scopes than generation | If a check passes but generation returns 401/403, AC9 marks it rejected. |
| Users paste a key into the wrong provider | The check fails with "This doesn't look like a valid Groq key", and nothing is stored. |

## 8. Testing

- **Unit:**
  - KeyBox round trip;
  - tampered ciphertext, wrong workspace (AAD) and unknown version all fail;
  - rotation;
  - each provider's check with `respx` (200 ok, 401/403 rejected, 5xx/timeout unavailable).
- **Integration:**
  - `test_ac1_*` save valid and invalid keys;
  - `test_ac3_reviewer_sees_status_cannot_manage`;
  - `test_ac4_key_never_in_responses_or_logs`;
  - `test_ac6_calls_use_workspace_key`;
  - `test_ac6_workspace_b_key_never_used_for_a`;
  - `test_ac7_no_key_fails_permanently_with_code`;
  - `test_ac8_connecting_key_requeues_no_key_documents`;
  - `test_ac9_rejected_key_marked_and_falls_back`;
  - `test_ac10_db_dump_has_no_plaintext`;
  - tenant meta-test.
- **Web:** settings page states (admin and reviewer), save, remove and test flows, banner, and the failure link.
