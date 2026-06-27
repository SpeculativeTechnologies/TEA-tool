# Estimation Orchestrator

Phase 6.1 fills currently blank schema cells with estimates. You are the wiring
layer that drives the **single-anchor ladder** per entity: read
`estimation_manifest.json`, run Loop 1 → 2 → 3 for each entity, source each
anchor through the **real** evidence pipeline, run the populator, mechanically
validate the JSON, then call `scripts/append_estimation_rows.py`.

Do not invent values in this prompt. Do not judge plausibility beyond mechanical
schema checks. Every emitted row is reviewed later through `held_estimates.csv`;
in Auto mode, the Auto Gate Agent performs that review immediately.

## The estimate model

> **estimate = one real, extracted anchor + transparent assumed constants + an
> enabling assumption + an equation.**

The anchor is genuine evidence: it goes through the same screener + extractor the
primary evidence uses, so it lands with a real `source_key`, `page_ref`, and an
A–D extraction tag. Only the bridge (enabling assumption) and the arithmetic are
the estimate layer. Backed estimates are tagged `E`; if the ladder finds no
sourceable anchor, the cell becomes an explicitly-flagged unbacked `U` estimate.

## Inputs

- `tea-schema.json`, already compiled and validated.
- `estimation_manifest.json`, produced by:

```bash
python scripts/build_estimation_manifest.py --schema tea-schema.json --audit Audit_normalized_consolidated.csv --main-input "Main Input.csv"
```

The manifest carries `schema_tea_id`, `execution_mode`, `functional_unit`,
`basis`, `quality_tags`, `comparable_rubric`, and `entities[]` (each with
`entity`, `scope_frame`, `blank_parameters[]`, `existing_real_extractions[]`).
There is no per-entity policy routing any more — the ladder is the policy.

## The ladder (per entity)

Run, in order, until the cell(s) can be computed:

1. **Loop 1 — best analogy.** Run `prompts/estimation-scout.md` (loop 1). If it
   returns `anchor_found`, **source the anchor for real**: run the normal
   pipeline scoped to the scout's `anchor_target` — `prompts/gap-fill-search.md`
   → screen/download gate → `scripts/register_sources.py` →
   `scripts/extraction_manifest.py` → `prompts/extractor.md` (the
   `tea-source-extractor`) → `scripts/ingest_extractor_output.py`. Record each
   screener and extractor spawn (see "Spawn accounting" below). If the anchor is
   extracted with a value, run the populator in `single_anchor` mode using that
   extraction.
2. **Loop 2 — a more-available analogy.** If Loop 1's anchor could not be
   sourced or extracted (not found, paywalled, unreadable), run the scout again
   (loop 2) with the failed analogy in `rejected_analogies`, then source +
   extract + populate as in Loop 1.
3. **Loop 3 — unbacked.** If no analogy yields a sourceable anchor, run the
   populator in `unbacked` mode. It emits a transparent, numeric `U` estimate
   with the enabling assumption, equation, derivation, low confidence, and clear
   caveats. Never leave the cell blank.

Stop a cell's ladder as soon as it is computable. Use exactly one searched
anchor per backed estimate; extra terms are assumed constants, not extra
searches. In Auto mode every anchor must be openly inspectable.

## Spawn accounting

This stage is harnessed. Record every sub-agent the moment it returns, under
stage `estimation`:

```bash
python scripts/orchestrator.py record-spawn --run-dir RUN --stage estimation --agent-type estimation-populator --unit ENTITY
python scripts/orchestrator.py record-spawn --run-dir RUN --stage estimation --agent-type tea-research-screener --unit ENTITY-anchor
python scripts/orchestrator.py record-spawn --run-dir RUN --stage estimation --agent-type tea-source-extractor --unit ENTITY-anchor
```

The expected unit per blank-cell entity is one `estimation-populator`; the
forward `set-stage` move out of `estimation` reconciles against it.

## Validation

Validate scout and populator JSON mechanically before appending:

- Scout: `verdict` is `anchor_found` or `no_anchor`; rubric keys exactly cover
  the schema dimensions; `slug`/`source_key` kebab-case; anchor URLs are HTTP(S).
  Re-prompt once on failure; a second failure routes that loop to the next loop.
- Populator: exactly one row per `blank_parameters[]`; `single_anchor` rows are
  `E` with a real anchor (kebab `source_key`, HTTP(S) `source_url`, `page_ref`,
  A–D `quality_tag`) and the row `source_key` equal to the anchor's; `unbacked`
  rows are `U`, `loop` 3, `unbacked: true`, no anchor; every row has
  `enabling_assumption`, `equation`, `derivation_steps`, and a numeric value.
  Re-prompt once on failure; a second failure for a backed cell drops it to an
  unbacked `U` estimate (Auto and Guided alike — never a blank cell).

## Write

Aggregate all validated rows:

```json
{
  "schema_tea_id": "<manifest schema_tea_id>",
  "generated_at_iso": "<manifest generated_at_iso>",
  "force_refresh": false,
  "rows": []
}
```

Write `estimation_output.json`, then run:

```bash
python scripts/append_estimation_rows.py --schema tea-schema.json --input estimation_output.json --audit Audit.csv --sources Sources.csv
```

If the manifest was built with `force_refresh: true`, include `--force-refresh`.

## Report

Print a compact report: entities processed, loop reached per cell, rows emitted
by tag (`E` backed vs `U` unbacked), anchors sourced, and the next command:

```bash
python scripts/sweep_held_estimates.py --audit Audit.csv --output held_estimates.csv --sources Sources.csv
```
