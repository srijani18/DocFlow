# F10: LLM gateway with fallback (tasks)

**Status:** Approved (2026-10-26)
**Prerequisite:** F15 (workspace keys). Manual (optional): connect Groq and OpenRouter keys in Settings.

- [x] **F10-T1: Routes and config** (AC1, AC9): `routing.py`; `LLM_ROUTE_*` settings replace the per-task model settings.
  - Tests: `test_route_parsing`, `test_ac9_unconnected_providers_skipped`.
- [x] **F10-T2: Circuit breaker** (AC4)
  - Tests: `test_ac4_opens_after_three_transient_failures`, `test_ac4_half_open_trial_closes_or_reopens`, `test_ac4_permanent_errors_dont_trip`.
- [x] **F10-T3: PDF to images and capabilities** (AC5): `pypdfium2`; Docker smoke test still passes.
  - Tests: `test_ac5_pdf_rendered_to_at_most_three_pngs`, `test_ac5_images_sent_unchanged`.
- [x] **F10-T4: Groq and OpenRouter providers** (AC2, AC3): the OpenAI-compatible adapter.
  - Tests: respx cases for json_schema/json_object, images, 429 + retry-after, 5xx, 400, malformed bodies.
- [x] **F10-T5: Fallback loop and logging** (AC1–AC3, AC7, AC8): migration `0007_llm_gateway`.
  - Tests: `test_ac1_first_success_stops`, `test_ac2_transient_and_invalid_fall_through`, `test_ac3_permanent_falls_through_then_permanent_if_all`, `test_ac7_calls_record_position_and_fallback`, `test_ac8_steps_unchanged`.
- [x] **F10-T6: Cache** (AC6)
  - Tests: `test_ac6_identical_request_hits_cache_without_provider_call`, `test_ac6_cache_never_crosses_workspaces`, `test_ac6_failures_not_cached`, `test_ac6_expired_entries_ignored`.
- [ ] **F10-T7: Live check and close-out:** one real call per configured provider; record the model IDs and limits in overview §8; spec status `Implemented`.
  - *2026-10-26:* Gemini done (plan §8). Groq and OpenRouter wait for keys in Settings.
