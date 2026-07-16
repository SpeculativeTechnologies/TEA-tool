# General TEA Workflow

This is the operator guide for one run of the General TEA Tool. Run commands
from the repository root and point `$RUN` at the run folder.

```powershell
$RUN = "runs/my-run"
```

Each run folder should contain `scope-summary.md`, `scope.md`,
`process-flow.md`, `data-requirements.md`, `tea-schema.json`, working CSVs,
source folders, search history, review queues, and final artifacts.

New users do not have to drive these stages by hand. The `/tea-data` skill
(`.claude/skills/tea-data/`) drives this workflow for them — after `/tea-scope`
has written the starting documents and `/tea-model` has built the model. It owns
durable run state and an issue ledger through `scripts/orchestrator.py` and routes
the phases below to a finalized, gap-free input set; `/tea-insights` then runs the
approved model on those inputs and explores the results. This guide remains the
execution authority the skill follows.

## Phase 0 - Setup

### 0.0 Select Execution Mode

Ask once at the beginning of the run:

- **Auto with Human Gates** (`auto_with_human_gates`, default): pause at each
  review gate for analyst decisions.
- **Auto** (`auto`): do not pause between stages. At every gate, run
  `prompts/auto-gate-agent.md`, write its decisions and `AUTO:` reasoning into
  the existing queue fields, immediately apply the queue, and continue.

Stage 0 records the choice in `tea-schema.json`. The choice applies only to the
current run and is not persisted as the default for future runs.

In Auto mode, maintain `$RUN/auto-run-log.md`. Record source-screening choices,
major assumptions, low-confidence decisions, flags, recoverable technical
errors and their fallback, and any unrecoverable technical errors. Ordinary
ambiguity is not a reason to interrupt the run.

Auto mode uses open evidence only. Search specifically for publicly inspectable
full text, tables, datasets, repository copies, government publications, open
journals/preprints, and official public technical documentation. Do not use
sources that require a subscription, institutional login, purchase, library
access, or an access request. A citation or abstract alone is not evidence the
Auto workflow can inspect.

### 0.1 Compile Schema

Run `prompts/stage0-schema-compile.md` with:

- `$RUN/scope.md`
- `$RUN/data-requirements.md`
- output folder `$RUN`

The agent writes:

- `$RUN/tea-schema.json`
- `$RUN/schema-open-questions.md`
- `$RUN/conventions/*.csv`

In Auto with Human Gates mode, Stage 0 asks or logs questions and blocks on
blocking ambiguity. In Auto mode, it makes the narrowest defensible assumption,
labels it, records confidence, and continues.

Validate the schema:

```powershell
python scripts/lib/schema.py "$RUN/tea-schema.json"
```

If convention files need to be scaffolded or refreshed:

```powershell
python scripts/scaffold_conventions.py --schema "$RUN/tea-schema.json" --output-dir "$RUN/conventions"
```

### 0.2 Build Working CSVs

```powershell
python scripts/build_csvs.py --schema "$RUN/tea-schema.json" --output-dir "$RUN"
```

This creates `Audit.csv`, `Sources.csv`, `Main Input.csv`, and source
directories.

For comparison projects, build each option run folder first, then materialize
the comparison shared inputs with
`scripts/materialize_shared_inputs.py --project-dir <comparison-project>`.

### 0.3 Materialize Analyst Inputs (optional)

When the analyst supplied values mapped to schema cells, record them in
`$RUN/user-inputs.csv` (and any synthetic source in `$RUN/user-sources.csv`,
which may use `source_role=analyst`), then materialize before searching:

```powershell
python scripts/orchestrator.py materialize-user-inputs --run-dir "$RUN"
```

This validates the inputs against the schema, blocks on two disagreeing fixed
inputs for one cell, merges the sources into `Sources.csv`, and writes analyst
rows into `Audit.csv` (`input_origin` of `analyst`/`extracted`/`shared`, and
`input_priority=fixed` when fixed). At consolidation, a fixed candidate outranks
a shared input, which outranks ordinary candidates; a fixed cell suppresses
replacement research, while non-fixed analyst evidence remains a normal candidate.

The `extracted` user-input origin is valid only for a source registered in
`provided-materials.json`; web-research results cannot enter through this lane.
`E` and `U` are also rejected here because estimates belong to Phase 6.

## Phase 1 - Master-List Search

This phase is mandatory for every run and every comparison option. Research
depth is not configurable: do not offer an estimation-led alternative or skip an
option because evidence is expected to be sparse. Estimation begins only in
Phase 6 after search, targeted gap fill, extraction, normalization, and
completeness review leave a cell blank.

### 1.1 Search

Run `prompts/master-list-search.md` with `$RUN/tea-schema.json`. The agent
returns candidate JSON only. Save it, for example:

```text
$RUN/search-history/master-list.json
```

Record the screener only after that JSON exists:

```powershell
python scripts/orchestrator.py record-spawn --run-dir "$RUN" `
    --stage evidence_collection --agent-type tea-research-screener --unit master-list
```

For a comparison parent run, use one unit per option
(`master-list:OPTION_ID`) and save the artifact under
`options/OPTION_ID/search-history/master-list.json`.

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

In Auto mode, the Auto Gate Agent performs this screening, records every
approve/reject decision in `$RUN/auto-run-log.md`, and continues immediately.
It approves only sources whose relevant evidence is openly inspectable; if a
publisher page is restricted, it first looks for a legitimate open repository
or author copy.

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

Record each targeted screener as `gap-fill:ENTITY` after its JSON exists (for a
comparison parent: `gap-fill:OPTION_ID:ENTITY`). A residual gap in this output is
evidence that the normal search lane did not find a usable source; it is not
permission to populate a value before Phase 6.

### 2.2 Screen And Download Gate

Review each gap-fill candidate:

- Does it cover at least one uncovered search-targetable parameter?
- Is `source_url` a real HTTP(S) source page?
- Is it non-duplicative, or intentionally retargeted with a new `source_key`?
- Does `field_coverage` list only the target entity or `REF`?
- Are residual gaps documented instead of filled with weak guesses?

Download approved files into `$RUN/gap fill sources/`.

In Auto mode, the Auto Gate Agent performs this screening and continues
immediately, using the same open-evidence-only rule.

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
`output_json` path. Record each slice as it returns so the spawn gate can
reconcile (a slice that genuinely cannot run — e.g. an unreadable source — is
recorded as a documented skip, never silently dropped):

```powershell
python scripts/orchestrator.py record-spawn --run-dir "$RUN" --stage extraction --agent-type tea-source-extractor --unit SLICE_ID
python scripts/orchestrator.py record-spawn --run-dir "$RUN" --stage extraction --agent-type tea-source-extractor --unit SLICE_ID --status skipped --reason "unreadable source, quarantined"
```

For a comparison parent, build the manifest inside every option folder and
record the parent-ledger unit as `OPTION_ID:SLICE_ID`.

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
In Auto mode, resolve every row with `accept` or `reject`; do not use
`re-extract` merely to ask the analyst.

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

In Auto mode, run the Auto Gate Agent and normalization agent as needed, apply
all rows, and continue without analyst input.

### 4.3 Resolve Cross-Source Disagreements

```powershell
python scripts/sweep_value_disagreements.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized.csv" --output "$RUN/value_disagreements.csv" --sources "$RUN/Sources.csv"
```

Fill `proposed_verdict` with `accept` or `reject`, plus `analyst_answer`.
Then:

```powershell
python scripts/apply_value_disagreements.py --audit "$RUN/Audit_normalized.csv" --queue "$RUN/value_disagreements.csv"
```

In Auto mode, the Auto Gate Agent resolves and applies every disagreement.

### 4.4 Consolidate To Main Input

If same-quality top candidates need a scope-fit tiebreaker, use
`prompts/scope-fit-agent.md` and save decisions to
`$RUN/stage5_scope_fit_decisions.csv`.

```powershell
python scripts/consolidate.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized.csv" --sources "$RUN/Sources.csv" --scope-fit-decisions "$RUN/stage5_scope_fit_decisions.csv" --audit-output "$RUN/Audit_normalized_consolidated.csv" --main-input "$RUN/Main Input.csv"
```

Pinned cells always outrank ordinary rows.

## Phase 5 - Completeness Review

Run the `tea-quality-reviewer` subagent over the consolidated inputs
(`Main Input.csv`, consolidated `Audit`, `Sources.csv`) to assess coverage,
quality, and residual gaps. Save its report to
`$RUN/reviews/completeness-review.md`, then record the pass (it is mandatory and
non-skippable):

```powershell
python scripts/orchestrator.py record-spawn --run-dir "$RUN" --stage completeness_review --agent-type tea-quality-reviewer --unit completeness_review
```

Review `$RUN/Main Input.csv` for coverage and quality.

Choose one of these exits:

- Proceed to estimation for remaining blanks.
- Run another gap-fill round for specific entities or reference values.
- Supply a value for the blank (analyst input).

No mode may finalize with a blank schema cell. In Auto mode, always proceed to
estimation for every remaining blank. In Auto with Human Gates mode, resolve each
remaining blank by approving an estimate or supplying a value; if neither is
available, the run stays blocked and resumable. Documented gaps are not an allowed
final state in either mode.

## Phase 6 - Estimation

### 6.1 Estimate Remaining Blanks

Build the estimation manifest:

```powershell
python scripts/build_estimation_manifest.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized_consolidated.csv" --main-input "$RUN/Main Input.csv" --output "$RUN/estimation_manifest.json"
```

Run `prompts/estimation-orchestrator.md` with the manifest. It drives the
**single-anchor ladder** per entity (`prompts/estimation-scout.md` →
`prompts/estimation-populator.md`):

- **Loop 1** picks the best analogy and sources its single anchor through the
  real pipeline (`gap-fill-search` → screen/download → `register_sources` →
  `extraction_manifest` → `extractor` → `ingest`), then the populator builds a
  backed `E` estimate from that real anchor + assumed constants + the enabling
  assumption.
- **Loop 2** retries with a more-likely-sourceable analogy if Loop 1's anchor
  could not be found/extracted.
- **Loop 3** emits a transparent, flagged **unbacked `U`** estimate when no
  anchor is sourceable. No cell is ever left blank.

Do not create or accept estimates outside this phase. In particular, do not put
research-worker derivations into `user-inputs.csv`, and do not label a derived
value `A`–`D`; those tags are reserved for real extracted evidence.

Record the estimation sub-agents as they run (the stage is harnessed):

```powershell
python scripts/orchestrator.py record-spawn --run-dir "$RUN" --stage estimation --agent-type estimation-populator --unit ENTITY
```

For a comparison parent, build one estimation manifest per option and use
`OPTION_ID:ENTITY` as the recorded unit.

Save the combined output as:

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

Fill `proposed_verdict` with `accept`, `reject`, or `analyst-override`. Both
backed (`E`) and unbacked (`U`) estimates are swept here; unbacked rows are
flagged in the queue notes so they get the most scrutiny. Overrides require
`analyst_value` and `analyst_units` and are re-tagged from `E`/`U` to `D`. Then:

```powershell
python scripts/apply_held_estimates.py --audit "$RUN/Audit_normalized_consolidated.csv" --queue "$RUN/held_estimates.csv"
```

In Auto mode, the Auto Gate Agent resolves every estimate immediately. Low
confidence is recorded for final review but does not leave the cell blank.

### 6.3 Normalize And Re-Consolidate Estimate Rows

```powershell
python scripts/normalize.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_normalized_consolidated.csv" --output "$RUN/Audit_post_estimation_normalized.csv" --conventions-dir "$RUN/conventions" --sources "$RUN/Sources.csv" --only-quality-tag E,U
```

Re-run the normalization flag and value disagreement gates for the updated
Audit file if queues are produced, then consolidate again:

```powershell
python scripts/consolidate.py --schema "$RUN/tea-schema.json" --audit "$RUN/Audit_post_estimation_normalized.csv" --sources "$RUN/Sources.csv" --scope-fit-decisions "$RUN/stage5_scope_fit_decisions.csv" --audit-output "$RUN/Audit_final_consolidated.csv" --main-input "$RUN/Main Input.csv"
```

## Phase 7 - Hand Off

Before finalizing, run the `tea-quality-reviewer` subagent once more over the
post-estimation consolidated inputs, save its report to
`$RUN/reviews/finalization-review.md`, and record the pass (mandatory,
non-skippable):

```powershell
python scripts/orchestrator.py record-spawn --run-dir "$RUN" --stage finalization --agent-type tea-quality-reviewer --unit finalization
```

### 7.1 Finalize Inputs

```powershell
python scripts/finalize_inputs.py --schema "$RUN/tea-schema.json" --main-input "$RUN/Main Input.csv" --sources "$RUN/Sources.csv" --audit "$RUN/Audit_final_consolidated.csv" --auto-run-log "$RUN/auto-run-log.md" --output-dir "$RUN/final"
```

Final artifacts:

- `$RUN/final/Main Input.csv`
- `$RUN/final/Reference Values.csv`
- `$RUN/final/run-manifest.md`
- `$RUN/final/auto-review.md` in Auto mode

Finalization is a hard completeness gate in **both** modes: every schema cell
must contain exactly one finite numeric model value (`normalized_value` or
`capex_usd`). Finalization fails if any cell is blank or non-numeric (pass
`--allow-gaps` only for an explicitly-draft intermediate manifest, never the
final hand-off). The Auto review compiles AI gate reasoning, assumptions,
estimates, flags, and technical errors for later review.

This is the end of the data pipeline: finalized, gap-free inputs. In the
orchestrator skills, `/tea-data` records the `inputs_finalized` gate here and hands
off to `/tea-insights`, which runs the approved model on these inputs and explores
the results. (Running the pipeline by hand, an analyst can instead feed
`final/Main Input.csv` to their own model.)

### 7.2 Finalize Comparison Project

For a comparison wrapper, after each option has been finalized:

```powershell
python scripts/validate_comparison_project.py --project-dir "$COMPARISON"
python scripts/finalize_comparison.py --project-dir "$COMPARISON"
```

This emits `final/shared-assumptions.csv`, `final/option-summary.csv`, and
`final/comparison-manifest.md` under the comparison project folder.

## Run Hygiene

- Keep source files in the run folder source buckets.
- Keep every LLM JSON output in `search-history/`, `extractions/`, or a named
  estimation file.
- Do not edit `Main Input.csv` directly except by rerunning the pipeline or
  materializing comparison shared inputs before search/extraction.
- When a script offers `--dry-run`, use it before file-moving or large updates.
- If a gate produces a queue, resolve and apply it before continuing.
