# F10: LLM gateway with fallback (plan)

**Status:** Draft (2026-10-26)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Approach

The F4 gateway already has the right shape (ADR-0003). F10 fills in the steps of `Gateway.generate`:

```
cache lookup ──hit──▶ log cache_hit, return
   │ miss
   ▼
for entry in route[task]:
    circuit open? ──yes──▶ log skipped, next
    adapt input (PDF → images if the provider can't read PDFs)
    call provider (timeout)
       ├─ ok + valid ──▶ circuit.success; store in cache; log ok; return
       ├─ invalid      ──▶ log invalid_output; next          (AC2)
       ├─ transient    ──▶ circuit.failure; log error; next  (AC2, AC4)
       └─ permanent    ──▶ log error; next                   (AC3)
all failed ──▶ raise Transient (any transient/invalid) else Permanent
```

## 2. Components

```
app/llm/routing.py          Route parsing from config ("provider:model,provider:model")
app/llm/circuit.py          CircuitBreaker (per provider:model; closed → open → half-open), injected clock
app/llm/cache.py            cache key, lookup, store (llm_cache table), 30-day expiry check
app/llm/inputs.py           ProviderCapabilities; pdf_to_images(data, max_pages=3, dpi=150) via pypdfium2
app/llm/providers/openai_compat.py  Chat Completions adapter shared by Groq and OpenRouter
                            (image_url data URIs, response_format json_schema or json_object + schema in prompt)
app/llm/providers/groq.py   base URL https://api.groq.com/openai/v1, capabilities: images ≤ 5, no PDF
app/llm/providers/openrouter.py base URL https://openrouter.ai/api/v1, capabilities: images, no PDF
app/llm/gateway.py          the loop above
```

- **Provider capabilities:** `{reads_pdf, reads_images, max_images, structured_output: "json_schema" | "json_object"}`. Gemini reads PDFs. Groq and OpenRouter get page images. When a provider supports only JSON mode, the schema goes into the instructions; our validation is unchanged either way.
- **Errors** map as in F4 (429/5xx/timeout → transient, with `retry_after` when given). Both OpenAI-compatible APIs return `{"error": {...}}`; a 429 response's `retry-after` header is honoured.

## 3. Data model (migration `0007_llm_gateway`)

```sql
ALTER TABLE llm_calls
  ADD COLUMN route_position integer NOT NULL DEFAULT 0,   -- 0 = first choice
  ADD COLUMN fallback boolean NOT NULL DEFAULT false,      -- true when route_position > 0
  ADD COLUMN input_mode text NULL;                         -- pdf | images | image
ALTER TABLE llm_calls DROP CONSTRAINT ck_llm_calls_outcome;
ALTER TABLE llm_calls ADD CONSTRAINT ck_llm_calls_outcome
  CHECK (outcome IN ('ok','error','invalid_output','cache_hit','skipped'));

CREATE TABLE llm_cache (
  key           text PRIMARY KEY,           -- sha256 of the request identity (spec D4)
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  task          text NOT NULL,
  provider      text NOT NULL,
  model         text NOT NULL,
  raw_json      text NOT NULL,              -- the validated answer, exactly as returned
  source_call_id uuid NULL REFERENCES llm_calls(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_cache_workspace_id ON llm_cache (workspace_id);
```

The cache key includes the workspace, so a cached answer can never cross tenants (AC6). Expired rows are ignored on read. Deleting them is a small sweep in the worker's idle loop, at most once an hour.

## 4. Configuration

```
LLM_ROUTE_CLASSIFY=gemini:gemini-flash-lite-latest,groq:meta-llama/llama-4-scout-17b-16e-instruct,openrouter:openrouter/free
LLM_ROUTE_EXTRACT=gemini:gemini-flash-lite-latest,groq:meta-llama/llama-4-scout-17b-16e-instruct,openrouter:openrouter/free
LLM_CACHE_TTL_DAYS=30
```

`LLM_CLASSIFY_MODEL` and `LLM_EXTRACT_MODEL` from F4/F5 are replaced by the routes. There are no provider keys in the app's environment: keys are per workspace (F15).

## 5. Security

- Keys live only in the backend environment. Request and response bodies are never logged.
- Only sample or synthetic documents go to any provider (constitution §5.5); this is unchanged.
- OpenRouter's free router picks the model; the model that actually answered is recorded from the response.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Fallback models are less accurate | F11 measures per model; routes are configuration. |
| Page images lose detail on dense invoices | 150 DPI, first 3 pages; F11 compares PDF and image accuracy. |
| `pypdfium2` adds memory on the 512 MB instance | One page rendered at a time and discarded; measured in the Docker smoke test. |
| Free model IDs rotate | Configuration only; a missing model looks like a permanent error for that entry and falls through. |

## 7. Testing

- **Unit:** route parsing; circuit breaker transitions with a fake clock; cache key stability and workspace separation; PDF to images (page count, PNG output); OpenAI-compatible adapter with `respx` (json_schema and json_object modes, images as data URIs, 429 with `retry-after`, 5xx, 400).
- **Integration (FakeProviders, real Postgres):** fallback order (AC1, AC2), permanent then success on the next entry (AC3), every entry failing (transient vs permanent), circuit skipping is logged (AC4), cache hit with no provider call (AC6), no cross-workspace hit, `llm_calls` columns (AC7), and the F4/F5 steps unchanged (AC8).
- **Manual (your keys):** one call per provider with the synthetic invoice; recorded in plan notes.
