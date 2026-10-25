# F4: Classification (plan)

**Status:** Draft (2026-10-25)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Approach

- **Minimal gateway (ADR-0003, first slice):** `app/llm/` with a `Provider` protocol, a `GeminiProvider` (httpx against the Generative Language REST API), a `FakeProvider`, the schema adapter, and `Gateway.generate(...)`, which calls the provider with a timeout, validates the JSON against the response schema, and logs an `llm_calls` row for every attempt. Routing, fallback, circuit breaker and cache are F10; the interface is built so F10 adds them without changing callers.
- **Classify step:** `app/pipeline/steps/classify.py`. Skips if the document already has `doc_type` (AC7). Otherwise sends the file (inline base64, ≤ 10 MB) with prompt `classify/v1` and the classification schema, then stores `doc_type`, `doc_type_confidence` and transitions to `EXTRACTING`, or to `NEEDS_REVIEW` with the note for `other` (AC3), in one transaction.

## 2. Gateway interface

```python
@dataclass(frozen=True)
class LlmRequest:
    task: Literal["classify", "extract"]
    prompt: Prompt                    # name, version, text (loaded from prompts/<task>/v<N>.md)
    parts: Sequence[TextPart | FilePart]
    response_schema: Mapping[str, object]   # bundled JSON Schema (refs inlined); adapted per provider
    context: CallContext              # workspace_id, document_id, job_id, attempt

class Gateway:
    async def generate(self, request: LlmRequest) -> LlmResult:   # LlmResult.data is schema-valid JSON
        # raises TransientLlmError(retry_after=…) | InvalidOutputError (transient for the queue) | PermanentLlmError
```

- **Gemini call:** `POST {base}/v1beta/models/{model}:generateContent` with `contents` (text + `inline_data`), `generationConfig.responseMimeType = "application/json"` and `responseJsonSchema` (the adapted schema), `temperature = 0`. Header `x-goog-api-key`. 60 s timeout. Usage from `usageMetadata`. Exact field names are verified against the live API when the provider is built.
- **Errors:** 429 / 500 / 503 / timeout → `TransientLlmError` (with `retry_after` from `RetryInfo` when present); 400 for bad input (e.g. unreadable file) → `PermanentLlmError`; JSON that fails schema validation → `InvalidOutputError` (logged as `invalid_output`, retried by the queue as transient, AC2).
- **Schema adapter:** inlines `$ref`s, drops `x-*`, `$id`, `$schema`, `$comment`, `examples`, and any keyword not in Gemini's supported list (kept in `app/llm/providers/gemini_schema.py`, unit tested).
- **Validation:** `jsonschema` (draft 2020-12) against the original, un-adapted schema, so adaptation can never loosen what we accept.

## 3. Data model (migration `0005_llm_calls_classification`)

```sql
CREATE TABLE llm_calls (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id     uuid NULL REFERENCES documents(id) ON DELETE SET NULL,
  job_id          uuid NULL REFERENCES jobs(id) ON DELETE SET NULL,
  task            text NOT NULL,                 -- classify | extract (F6+: validate, embed…)
  provider        text NOT NULL,
  model           text NOT NULL,
  prompt_version  text NOT NULL,                 -- e.g. classify/v1
  attempt         integer NOT NULL,
  outcome         text NOT NULL CHECK (outcome IN ('ok','error','invalid_output')),
  error_type      text NULL,
  input_tokens    integer NULL,
  output_tokens   integer NULL,
  cost_usd        numeric(12,6) NULL,            -- estimated from the price table
  latency_ms      integer NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_calls_workspace_id ON llm_calls (workspace_id);
CREATE INDEX ix_llm_calls_document_id ON llm_calls (document_id);

ALTER TABLE documents
  ADD COLUMN doc_type text NULL CHECK (doc_type IN ('invoice','receipt','purchase_order','other')),
  ADD COLUMN doc_type_confidence real NULL CHECK (doc_type_confidence BETWEEN 0 AND 1);
```

- `llm_calls` is written in its **own short transaction** (not the step's), so failed and invalid attempts are kept even when the step rolls back (AC4).
- Prompt files: `app/llm/prompts/classify/v1.md`. Price table: `app/llm/prices.v1.json` (`{provider: {model: {input_per_mtok, output_per_mtok}}}`), with unknown models logged with `cost_usd = NULL`, never a guess.

## 4. Schema

`schemas/classification.v1.json` (`x-schema-id: docflow/classification/v1`):

```json
{ "type": "object", "additionalProperties": false, "required": ["doc_type", "confidence"],
  "properties": {
    "doc_type":   { "enum": ["invoice", "receipt", "purchase_order", "other"] },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 } } }
```

## 5. API changes

`Document` gains `doc_type: DocType | null` and `doc_type_confidence: number | null`. No new endpoints.

## 6. Configuration

`GEMINI_API_KEY` (secret), `GEMINI_BASE_URL` (default `https://generativelanguage.googleapis.com`), `LLM_CLASSIFY_MODEL` (default `gemini-flash-lite-latest`), `LLM_CLASSIFY_PROMPT` (default `classify/v1`), `LLM_TIMEOUT_SECONDS` (60). CI uses `FakeProvider`; no key needed.

## 7. Security and data

- The API key is only in the backend environment and never logged; request/response bodies are not logged (they contain document content).
- Only sample/synthetic documents may be uploaded (F2 AC7, constitution §5.5).
- A provider lint rule (ruff banned-api, already configured) keeps HTTP calls to LLM APIs inside `app/llm/providers/`.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Model alias changes behaviour or is retired | Model ID is config; the `llm_calls.model` column records what actually ran; evals (F11) catch regressions. |
| Free-tier rate limits during bursts | Queue backoff with `retry_after` (F3). One job at a time. |
| Gemini rejects parts of our JSON Schema | Adapter + unit tests against Gemini's supported subset; validation is against the original schema anyway. |

## 9. Testing

- **Unit:** schema adapter; Gemini provider with `respx` (success, 429 with RetryInfo, 503, timeout, 400, malformed JSON); cost estimate; prompt loader.
- **Integration (FakeProvider, real Postgres):** `test_ac1_*` labels and confidence stored; `test_ac2_invalid_output_logged_and_retried`; `test_ac3_other_skips_extraction`; `test_ac4_every_attempt_logged`; `test_ac7_rerun_makes_no_call`.
- **Manual (local, your key):** classify the synthetic sample invoice; record the model list and free-tier limits from AI Studio in overview §8.
