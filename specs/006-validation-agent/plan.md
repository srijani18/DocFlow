# F6: Validation agent (plan)

**Status:** Approved (2026-10-26)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Pipeline change

`EXTRACTING → VALIDATING → APPROVED | NEEDS_REVIEW`. The extract step now advances to `VALIDATING`, and a new `validate` step (`app/pipeline/steps/validate.py`) does the rest. Document statuses add `VALIDATING` and `APPROVED`; documents add `approved_at`, `approved_by_user_id` (null when the agent approved) and `approved_by_agent`.

## 2. Components

```
app/validation/
  checks.py     pure functions: check_line_items, check_totals, check_gstins, check_tax_types,
                check_dates, check_duplicate(ctx), check_known_vendor(ctx) -> list[Issue]
  gstin.py      is_valid_gstin(value): format + mod-36 checksum (Luhn-style weights 1/2 over 14 chars)
  money.py      amounts_match(a, b): |a-b| <= max(1.00, 0.5% of max(|a|,|b|))
  agent.py      ValidationAgent.run(ctx) -> AgentResult(issues, fixed_data | None, rounds)
  models.py · repository.py · service.py · schemas.py
app/llm/prompts/validate/v1.md
```

**Agent loop (D1):**

```
issues = run_checks(data)
for round in 1..2:
    fixable = [i for i in issues if i.check in {line_items, totals, gstin}]
    if not fixable: break
    ask model (gateway, task "validate"):
      the document + "these checks failed: … current values at paths: …";
      schema {fixes: [{path, value, confidence, reason}]}
    candidate = apply(data, fixes)        # only to the paths listed in the fixable issues
    new_issues = run_checks(candidate)
    if score(new_issues) < score(issues): data, issues = candidate, new_issues   # AC4
    else: break                           # no progress: stop
```

`score` counts errors × 10 + warnings. A candidate must still validate against the document schema.

## 3. Data model (migration `0009_validation`)

```sql
CREATE TABLE validation_issues (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,  -- the version checked
  check_name    text NOT NULL,
  severity      text NOT NULL CHECK (severity IN ('error','warning','info')),
  paths         text[] NOT NULL,
  message       text NOT NULL,
  fixed_by_agent boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_validation_issues_workspace_id ON validation_issues (workspace_id);
CREATE INDEX ix_validation_issues_extraction ON validation_issues (extraction_id);
ALTER TABLE documents ADD COLUMN approved_at timestamptz, ADD COLUMN approved_by_user_id uuid REFERENCES users(id),
  ADD COLUMN approved_by_agent boolean NOT NULL DEFAULT false;
-- status CHECK gains VALIDATING and APPROVED; llm_calls task gains 'validate'
```

**Duplicate check:** a query on `documents` joined to their current extraction data, for the same workspace: same `vendor_name` (case-insensitive) or vendor GSTIN, and the same document number, excluding the document itself. An index on `(workspace_id, vendor_name)` already exists (F5).

## 4. API

- `Document` gains `approved_at`, `approved_by_agent` and `issue_counts {error, warning, info}`.
- `GET …/documents/{id}/issues` returns the issues for the current extraction.
- The UI shows issues on the detail page and in review (F7).

## 5. Evals (AC10)

`python -m evals --agent` runs the validate step after extraction (with the in-memory recorder and tools that have no database: duplicates are checked within the eval dataset). The report adds a "before / after agent" column per model, and counts "changed right→wrong" against the truth.

## 6. Risks

| Risk | Mitigation |
|---|---|
| The agent makes correct values wrong | A correction is kept only if checks improve, and AC10 measures right→wrong changes. |
| GSTIN checksum false negatives on real documents | The algorithm is tested against published examples; a checksum failure is `error` only when the format is valid. |
| More LLM calls per document | At most 2 extra calls, only when a fixable check fails; clean documents cost nothing extra. |

## 7. Testing

- **Unit:** every check (passing and failing cases, tolerance edges, skipped when not applicable), GSTIN checksum vectors, agent loop with a fake model (fixes, no progress, worse result discarded, round limit), and auto-approve rules.
- **Integration:** pipeline `EXTRACTING → VALIDATING → APPROVED/NEEDS_REVIEW`, an `agent_fix` version saved, issues stored per version, idempotent re-run, duplicate across documents, workspace isolation of the duplicate and known-vendor checks.
- **Eval:** dataset v2 with 4 broken documents; before/after numbers committed (Phase 3 "done when").
