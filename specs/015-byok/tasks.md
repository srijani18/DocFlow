# F15: Bring your own AI keys (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F4/F5 gateway. Built **before** F10.

- [ ] **F15-T1: KeyBox and master keys** (AC10): `crypto.py`, `BYOK_MASTER_KEYS`, `make byok-key`.
  - Tests: round trip, tamper, AAD mismatch, unknown version, rotation.
- [ ] **F15-T2: Table and repository** (AC2, AC10): migration `0007_ai_keys` (`workspace_ai_keys`, `documents.failure_code`).
  - **Done when:** migrations-check and the tenant meta-test pass.
- [ ] **F15-T3: Key checks per provider** (AC1, AC5): Gemini, Groq and OpenRouter list-models calls.
  - Tests: respx ok / rejected / unavailable.
- [ ] **F15-T4: Endpoints** (AC1–AC5): list, save, delete, test; admin-only mutations; regenerate the client.
  - Tests: `test_ac1_*`, `test_ac2_*`, `test_ac3_*`, `test_ac4_*`, `test_ac5_*`.
- [ ] **F15-T5: Gateway uses workspace keys** (AC6, AC7, AC9): per-request keys; `NoCredentialsError` mapped to the permanent `no_ai_key`; rejected keys marked; `GEMINI_API_KEY` removed from app settings.
  - Tests: `test_ac6_*`, `test_ac7_*`, `test_ac9_*`, `test_ac4_key_never_in_logs`.
- [ ] **F15-T6: Auto-requeue on connect** (AC8)
  - Tests: `test_ac8_connecting_key_requeues_no_key_documents`, other failures not requeued.
- [ ] **F15-T7: Web settings, banner and failure link**
  - Tests: admin and reviewer views, save/remove/test, no-key banner, the link on `no_ai_key` failures.
- [ ] **F15-T8: Live check:** add your Gemini key through Settings, process the sample invoice, and confirm it used the workspace key (`llm_calls`). Spec status `Implemented`.
