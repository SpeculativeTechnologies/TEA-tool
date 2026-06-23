# General TEA Workflow

This is the operator guide for one run of the General TEA Tool. Run commands
from the repository root and point `$RUN` at the run folder.

```powershell
$RUN = "runs/my-run"
```

Each run folder should contain `scope.md`, `data-requirements.md`,
`tea-schema.json`, working CSVs, source folders, search history, review queues,
and final artifacts.

## Phase 0 - Setup

### 0.1 Compile Schema

Run `prompts/stage0-schema-compile.md` with:

- `$RUN/scope.md`
- `$RUN/data-requirements.md`
- output folder `$RUN`

The agent writes:

- `$RUN/tea-schema.json`
- `$RUN/schema-open-questions.md`
- `$RUN/conventions/*.csv`

Stage 0 must ask or log questions when the input docs are ambiguous. Do not
continue downstream while blocking questions remain.

Validate the schema:

```powershell
python scripts/lib/schema.py "$RUN/tea-schema.json"
```

If convention files need to be scaffolded or refreshed:

```powershell
python scripts/scaffold_conventions.py --schema "$RUN/tea-schema.json" --output-dir "$RUN/conventions"
```

### 0.2 Build Working CSVs

If the run has pinned values, create `$RUN/pinned-inputs.csv` from
`templates/pinned-inputs.template.csv` before building.

```powershell
python scripts/build_csvs.py --schema "$RUN/tea-schema.json" --output-dir "$RUN"
```

This creates `Audit.csv`, `Sources.csv`, `Main Input.csv`, source directories,
and, when present, loads `pinned-inputs.csv`.

If pinned inputs are added after the build step:

```powershell
python scripts/load_pinned_inputs.py --schema "$RUN/tea-schema.json" --run-dir "$RUN"
```

## Phase 1 - Master-List Search

### 1.1 Search

Run `prompts/master-list-search.md` with `$RUN/tea-schema.json`. The agent
returns candidate JSON only. Save it, for example:

```text
$RUN/search-history/master-list.json
```

Reference-value searches must be context-free. They should not mention this
TEA's system, entities, or route.

### 1.2 Screen And Download Gate

Review each candidate before downloading:

- Is the source real and locatable from `source_url`?
- Does `field_coverage` use only valid schema entity/parameter pairs?
- Is the source boundary plausibly inside the covered entity scope frame?
- Is the quality estimate credible?
- For `REF` reference values, is the query context-free?

Download approved files into `$RUN/master list sources/`. Do not register
undownloaded candidates.

### 1.3 Normalize Filenames

Dry-run first:

```powershell
python scripts/rename_sources.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/master-list.json" --source-dir "$RUN/master list sources"
```

After reviewing matches:

```powershell
python scripts/rename_sources.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/master-list.json" --source-dir "$RUN/master list sources" --apply
```

The normalized filename form is `{entity_or_chain}_{source_key}.{ext}`.

### 1.4 Register Sources

```powershell
python scripts/register_sources.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/master-list.json" --source-dir "$RUN/master list sources" --sources "$RUN/Sources.csv"
```

Rows are written with `source_role=extraction` and `source_url`.

## Phase 2 - Gap-Fill Search

Run this phase only for entities or `REF` parameters still uncovered after
master-list screening.

### 2.1 Search Per Entity

Run `prompts/gap-fill-search.md` once per target entity. Use the schema default
cap when present, otherwise at most 5 candidates. Save outputs such as:

```text
$RUN/search-history/gap-fill-ENTITY.json
```

### 2.2 Screen And Download Gate

Review each gap-fill candidate:

- Does it cover at least one uncovered first-class parameter?
- Is `source_url` a real HTTP(S) source page?
- Is it non-duplicative, or intentionally retargeted with a new `source_key`?
- Does `field_coverage` list only the target entity or `REF`?
- Are residual gaps documented instead of filled with weak guesses?

Download approved files into `$RUN/gap fill sources/`.

### 2.3 Normalize Filenames

```powershell
python scripts/rename_sources.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/gap-fill-ENTITY.json" --source-dir "$RUN/gap fill sources" --mode gap --entity ENTITY --uncovered-parameters parameter_a,parameter_b
```

Add `--apply` only after reviewing the dry-run.

### 2.4 Register Sources

```powershell
python scripts/register_sources.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/gap-fill-ENTITY.json" --source-dir "$RUN/gap fill sources" --sources "$RUN/Sources.csv" --mode gap --entity ENTITY --uncovered-parameters parameter_a,parameter_b
```

## Phase 3 - Extraction

### 3.1 Build Manifest And Run Batches

Build the extraction manifest from accepted search JSON and registered sources:

```powershell
python scripts/extraction_manifest.py --schema "$RUN/tea-schema.json" --input "$RUN/search-history/master-list.json" --input "$RUN/search-history/gap-fill-ENTITY.json" --source-dir "$RUN/master list sources" --source-dir "$RUN/gap fill sources" --sources "$RUN/Sources.csv" --output "$RUN/extractions/extraction_manifest.json"
```

Get the next resumable batch:

```powershell
python scripts/next_batch.py --manifest "$RUN/extractions/extraction_manifest.json"
```

Run `prompts/extractor.md` once per slice. Save each output JSON to the slice's
`output_json` path.

### 3.2 Resolve Scope-Relevance Holds

Ingest extracted rows:

```powershell
python scripts/ingest_extractor_output.py --schema "$RUN/tea-schema.json" --input "$RUN/extractions/SOURCE.extraction.json" --audit "$RUN/Audit.csv" --sources "$RUN/Sources.csv" --manifest "$RUN/extractions/extraction_manifest.json"
```

Sweep unresolved holds:

```powershell
python scripts/sweep_held_questions.py --audit "$RUN/Audit.csv" --output "$RUN/held_questions.csv"
```

Fill `proposed_verdict` with `accept`, `reject`, or `re-extract`, plus
`analyst_answer`. Then apply:

```powershell
python scripts/apply_held_verdicts.py --audit "$RUN/Audit.csv" --queue "$RUN/held_questions.csv"
```

Normalization hard-blocks while any row still has `relevance_status=hold`.

### 3.3 Ingest Complete Set

Repeat ingestion until every manifest slice is complete or intentionally left
out. Keep raw extractor outputs in `$RUN/extractions/`.

## Phase 4 - Normalize And Consolidate

### 4.1 Normalize

```powershell
python scripts/normalize.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit.csv" --output "$RUN/Audit_normalized.csv" --conventions-dir "$RUN/conventions" --sources "$RUN/Sources.csv"
```

### 4.2 Resolve Normalization Flags

```powershell
python scripts/sweep_normalization_flags.py --audit "$RUN/Audit_normalized.csv" --output "$RUN/normalization_flags.csv"
```

Fill `proposed_action` with `agent calc` or `reject`, plus `analyst_answer`.
Use `prompts/normalization-agent.md` for rows needing agent calculation. Then:

```powershell
python scripts/apply_normalization_flags.py --audit "$RUN/Audit_normalized.csv" --queue "$RUN/normalization_flags.csv"
```

### 4.3 Resolve Cross-Source Disagreements

```powershell
python scripts/sweep_value_disagreements.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized.csv" --output "$RUN/value_disagreements.csv" --sources "$RUN/Sources.csv"
```

Fill `proposed_verdict` with `accept` or `reject`, plus `analyst_answer`.
Then:

```powershell
python scripts/apply_value_disagreements.py --audit "$RUN/Audit_normalized.csv" --queue "$RUN/value_disagreements.csv"
```

### 4.4 Consolidate To Main Input

If same-quality top candidates need a scope-fit tiebreaker, use
`prompts/scope-fit-agent.md` and save decisions to
`$RUN/stage5_scope_fit_decisions.csv`.

```powershell
python scripts/consolidate.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized.csv" --sources "$RUN/Sources.csv" --scope-fit-decisions "$RUN/stage5_scope_fit_decisions.csv" --audit-output "$RUN/Audit_normalized_consolidated.csv" --main-input "$RUN/Main Input.csv"
```

Pinned cells always outrank ordinary rows.

## Phase 5 - Completeness Review

Review `$RUN/Main Input.csv` for coverage and quality.

Allowed exits:

- Proceed to estimation for remaining blanks.
- Run another gap-fill round for specific entities or reference values.
- Accept documented gaps.

There is no re-scoping or re-lumping stage.

## Phase 6 - Estimation

### 6.1 Estimate Remaining Blanks

Build the estimation manifest:

```powershell
python scripts/build_estimation_manifest.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized_consolidated.csv" --main-input "$RUN/Main Input.csv" --output "$RUN/estimation_manifest.json"
```

Run `prompts/estimation-orchestrator.md` with the manifest. It routes entity
work to `prompts/estimation-scout.md` and `prompts/estimation-populator.md` as
needed. Save the combined output as:

```text
$RUN/estimation_output.json
```

Append estimate rows and register their cited sources:

```powershell
python scripts/append_estimation_rows.py --schema "$RUN/tea-schema.json" --input "$RUN/estimation_output.json" --audit "$RUN/Audit_normalized_consolidated.csv" --sources "$RUN/Sources.csv"
```

### 6.2 Resolve Held Estimates

```powershell
python scripts/sweep_held_estimates.py --audit "$RUN/Audit_normalized_consolidated.csv" --output "$RUN/held_estimates.csv" --sources "$RUN/Sources.csv"
```

Fill `proposed_verdict` with `accept`, `reject`, or `analyst-override`.
Overrides require `analyst_value` and `analyst_units` and are re-tagged from
`E` to `D`. Then:

```powershell
python scripts/apply_held_estimates.py --audit "$RUN/Audit_normalized_consolidated.csv" --queue "$RUN/held_estimates.csv"
```

### 6.3 Normalize And Re-Consolidate Estimate Rows

```powershell
python scripts/normalize.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized_consolidated.csv" --output "$RUN/Audit_post_estimation_normalized.csv" --conventions-dir "$RUN/conventions" --sources "$RUN/Sources.csv" --only-quality-tag E
```

Re-run the normalization flag and value disagreement gates for the updated
Audit file if queues are produced, then consolidate again:

```powershell
python scripts/consolidate.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_post_estimation_normalized.csv" --sources "$RUN/Sources.csv" --scope-fit-decisions "$RUN/stage5_scope_fit_decisions.csv" --audit-output "$RUN/Audit_final_consolidated.csv" --main-input "$RUN/Main Input.csv"
```

## Phase 7 - Hand Off

### 7.1 Finalize Inputs

```powershell
python scripts/finalize_inputs.py --schema "$RUN/tea-schema.json" --main-input "$RUN/Main Input.csv" --sources "$RUN/Sources.csv" --output-dir "$RUN/final"
```

Final artifacts:

- `$RUN/final/Main Input.csv`
- `$RUN/final/Reference Values.csv`
- `$RUN/final/run-manifest.md`

Stop here. The analyst runs their own model outside this workflow.

## Run Hygiene

- Keep source files in the run folder source buckets.
- Keep every LLM JSON output in `search-history/`, `extractions/`, or a named
  estimation file.
- Do not edit `Main Input.csv` directly except by rerunning the pipeline or
  supplying pinned inputs before build.
- When a script offers `--dry-run`, use it before file-moving or large updates.
- If a gate produces a queue, resolve and apply it before continuing.

## Human Gate Memo Templates

Use these short memos for gates that are not already fully captured by a queue
CSV. Store them in `$RUN/review-history/`.

### Source Screening Memo

```markdown
# Source Screening - <phase/entity/date>

Decision: approved / rejected / needs follow-up
Candidate file:
Source key:
Source URL:
Covered cells:
Reason:
Downloader notes:
```

### Completeness Review Memo

```markdown
# Completeness Review - <date>

Main Input reviewed:
Filled cells:
Residual gaps:
Low-quality cells to accept:
Cells needing another gap-fill round:
Decision: proceed to estimation / run gap-fill / accept gaps
Analyst rationale:
```

### Final Hand-Off Memo

```markdown
# Final Hand-Off - <date>

Final folder:
Main Input:
Reference Values:
Run manifest:
Pinned cells:
Residual gaps:
Validation targets surfaced:
Known caveats before model use:
```
