# F11: Eval suite (plan)

**Status:** Approved (2026-10-26)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Layout

```
evals/                                 (repo root: data and results)
  dataset/
    manifest.v1.json                   [{id, file, content_type, doc_type, schema_id, truth, source, licence}]
    files/                             PDFs, JPEGs, PNGs
  samples/                             (F5) generator and the 3 smoke samples
  reports/<run-id>.json|.md            committed when quoted
apps/api/evals/                        (runner: same toolchain as the API)
  build_dataset.py                     synthetic generator (extends F5's) + CORD import/mapping
  scoring.py                           exact / fuzzy / numeric rules from x-eval; field walk; line items by index
  runner.py                            run(models, dataset, limit) → RunResult
  report.py                            JSON + Markdown (tables per model, comparison)
  __main__.py                          CLI: python -m evals --models gemini:…,groq:… --limit 20 --out ../../evals/reports
```

## 2. How a run works

1. Load the manifest; pick `limit` documents deterministically (stable order by id).
2. For each model, for each document:
   - call the gateway's classify, then extract using the **true** document type. This keeps extraction accuracy separate from classification mistakes; classification is scored on its own.
   - Use a one-entry route (that model only), with the cache disabled and an in-memory call recorder instead of `llm_calls`.
3. Score each labelled field against the truth with its `x-eval` rule (from the bundled schema), then aggregate.
4. Write `<run-id>.json` (every field result, for later analysis) and `<run-id>.md`.

**Run id:** `YYYYMMDD-HHMM-<short commit>-<4 random hex>`.

## 3. Gateway changes it needs

- A `CallRecorder` protocol. `DbCallRecorder` (today's behaviour) writes `llm_calls`; `MemoryCallRecorder` keeps calls in memory for evals (AC8).
- `use_cache: bool` per request (false for evals, AC6).
- A gateway built with an explicit route, so each model can be evaluated alone.

## 4. Scoring details

- Fields come from walking the truth instance (dotted paths, same as the confidence paths). Each leaf's rule is the `x-eval` of the matching schema node; leaves without a rule use `exact`.
- Numbers are compared with `Decimal`. Strings are NFC-normalised and trimmed; fuzzy also case-folds and collapses whitespace.
- **Masking:** a truth file may list `unlabelled: [paths]` (needed for CORD, which has no vendor GSTIN, dates and so on); those paths are skipped.
- **Aggregates:**
  - field accuracy = correct / scored;
  - per-field accuracy = the same per path, with array indices replaced by `*`;
  - document all-correct rate;
  - classification accuracy;
  - invalid-answer rate;
  - latency (median, p95) and cost per document from the recorded calls.

## 5. CI (`.github/workflows/evals.yml`)

- Triggers: `schedule` (nightly), `workflow_dispatch`, and `pull_request` with the `eval` label (`types: [labeled, synchronize]`, run only when the label is present).
- Steps:
  1. Set up uv.
  2. Run `make eval MODELS=… LIMIT=20`.
  3. Upload `evals/reports/` as an artifact.
  4. On pull requests, post the Markdown as a comment (`gh pr comment`, using `GITHUB_TOKEN` with `pull-requests: write`).
- No keys: the step prints "Skipping evals: no provider keys configured" and exits 0 (AC7).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Synthetic data overstates accuracy | CORD photos add real-world receipts; the report shows per-source accuracy. |
| CORD labels don't map cleanly (Indonesian rupiah, partial fields) | Map only what's labelled; mask the rest (§4). |
| Free-tier limits during nightly runs | 20 documents × 2 tasks × 2 models = 80 calls, far below daily limits. |

## 7. Testing

- **Unit:**
  - each scoring rule and its edge cases (nulls, tolerance, NFC, case);
  - line items by index with missing or extra items;
  - masking;
  - aggregation on hand-made results;
  - the Markdown report snapshot;
  - the run id format;
  - the manifest validates (every truth validates against its schema; files exist; licence present).
- **Integration:** a full run on 3 documents with `FakeProvider` (no network, no database).
- **Manual:** the first real baseline run, committed as the Phase 2 "done when".


## 8. Implementation notes (F11-T1 to T5)

- **Gateway hooks:** `CallRecorder` (`DbCallRecorder` for the app, `MemoryCallRecorder` for evals) and an optional sessionmaker. Without one there's no cache and no database at all (AC8).
- **Failed extractions score every field wrong.** Otherwise truth fields that are legitimately `null` would "match" a missing answer and inflate accuracy. A test caught this.
- **Rate limits:** `--pace` waits between calls (CI uses 4 s), and temporary errors are retried twice, honouring `retry_after`. The circuit breaker is disabled for evals so every document is measured.
- **Sampling:** `--limit` rotates through (source, type) groups, so even 4 documents cover CORD and every synthetic type.
- **Dataset v1** (`make eval-dataset`): 8 invoices, 6 receipts and 6 POs, synthetic, every second one a rotated, noisy JPEG "photo"; plus 10 CORD v2 test receipts (CC BY 4.0), resized to ≤1600 px. 1.4 MB in total. CORD masks merchant, dates, payment and currency fields, which CORD doesn't label (amounts are in IDR).
- **CI:** `.github/workflows/evals.yml` runs nightly (02:00 IST), on demand, and on pull requests labelled `eval`. It uploads the report and comments it on the PR, and exits 0 with "Skipping evals" when no keys are configured.
