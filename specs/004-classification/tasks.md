# F4: Classification (tasks)

**Status:** Approved (2026-10-25)
**Prerequisite:** F3-T3 (pipeline runner). Manual: `GEMINI_API_KEY` in `.env` (AI Studio, free, no card).

- [x] **F4-T1: `llm_calls` table and price table** (AC4) — migration `0005_llm_calls_classification`; `prices.v1.json`; cost estimate.
  - Tests: `test_cost_estimate_from_price_table`, `test_unknown_model_cost_is_null`. **Done when:** migrations-check and tenant meta-test pass.
- [x] **F4-T2: Gateway core** (AC2, AC4, AC5, AC6) — `LlmRequest`, `Gateway.generate`, prompt loader, schema adapter, validation, call logging in its own transaction, `FakeProvider`.
  - Tests: `test_ac2_invalid_output_raises_and_is_logged`, `test_ac4_every_attempt_logged_with_tokens_cost_latency`, `test_ac6_prompt_loaded_by_version`, `test_schema_adapter_inlines_refs_and_strips_x_keys`.
- [ ] **F4-T3: Gemini provider** (AC5) — httpx adapter; error mapping; `retry_after` from `RetryInfo`.
  - Tests: `respx` cases for 200, 429 + RetryInfo, 503, timeout, 400, non-JSON. **Done when:** a manual call with your key classifies `evals/samples/synthetic-invoice-001.pdf` (created in F5-T1).
- [x] **F4-T4: Classification schema, prompt and step** (AC1, AC3, AC7).
  - Tests: `test_ac1_label_and_confidence_stored`, `test_ac3_other_goes_to_needs_review_with_note`, `test_ac7_rerun_makes_no_call`.
- [x] **F4-T5: Show type in the UI** (AC1) — type and confidence on list and detail (regenerate client).
  - Tests: `AC1: list shows type and confidence`.
- [ ] **F4-T6: Close-out** — record real Gemini model IDs and free-tier limits (date-stamped) in overview §8; spec status `Implemented`.
