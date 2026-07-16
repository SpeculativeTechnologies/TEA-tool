# Insights and iteration (/tea-insights)

The execution contract for `/tea-insights` (Skill 4): run the already-approved
`model.py` on the finalized inputs, present the real results, then surface insights
and propose new visualizations tied to the user's decision — and iterate
open-endedly on plots and light model tweaks. `/tea-insights` only starts once
**both** `inputs_finalized` (from `/tea-data`) and `model_approved` (from
`/tea-model`) are recorded and valid (`status` → `approvals.valid`); otherwise send
the user back to the skill that owns the missing gate.

Keep the bookkeeping invisible: talk about "the model", "the charts", and "what the
numbers say", not schema cells and CSV columns. The plots here are **real** (model
run on finalized data); the DUMMY figures from `/tea-model` are a separate
structure check in `plots-dummy/` and are never overwritten.

## Gate check (start)

Read `status`/`validate-resume`:

- Require `inputs_finalized` in `approvals.valid`; else stop and send the user to
  `/tea-data` (the data is not finalized).
- Require `model_approved` in `approvals.valid`; else send the user to `/tea-model`
  to re-approve (the model file changed outside this skill).
- If the run is already `complete`, this skill is **re-runnable** — re-open it,
  re-present, and offer further iteration without rewinding the stage.

## 1. Run the model + present results

After `/tea-data` produced the finalized, fully-populated `Main Input.csv`, run the
already-approved model on it — this run **is** the deliverable. See
`references/model-building.md` for the model contract.

```
python "runs/<project>/model.py" --inputs "runs/<project>/Main Input.csv" \
    --outdir "runs/<project>/plots" --results "runs/<project>/model-results.json"
```

The real run writes `plots/` and `model-results.json`; the dummy figures from
`/tea-model` remain in `plots-dummy/` (**not** overwritten). Present the **real**
plots, the headline metric(s), and the key sources/assumptions. If the run has
benchmarks, present the validation comparison
explicitly — computed value vs. researched literature benchmark (with its source)
for each target, from `results["validation"]`. Flag any benchmark that ended up
**estimated** rather than literature-sourced (`E`/`U`): an estimated benchmark is
not an independent check.

## 2. Surface insights + propose new plots

This is the distinctive work of this skill. Read both sides:

- **What the model produced** — `model-results.json` (the headline metric plus
  every intermediate block the model emitted: cost breakdown, tornado/sensitivity,
  process groups, mass balance, cash flow, validation, …) and the rendered plots.
- **Why the user is doing this** — the starting documents (`scope-summary.md`;
  `scope.md` decision,
  headline metrics, scenarios, validation targets; `model-requirements.md`;
  `data-requirements.md`; `process-flow.md`) **and the materials the user
  originally supplied** (`provided-materials.json` plus the registered files). For
  large supplied materials, fan out a read-only `tea-materials-analyst` rather than
  reading them inline; apply each material's sensitivity policy.

Name the **insights the real data surfaces**: what dominates the headline number,
what the sensitivity analysis says moves it most, where the computed value agrees
with or diverges from the benchmarks, and anything surprising relative to the
user's framing or their supplied documents.

Then propose a short menu (**~3–6**) of **new visualizations**, with discipline:

- **Pair each suggestion with the specific question about the user's idea it would
  help answer** — tie it to their decision, not to chart aesthetics. The question
  is the point; the chart is the means. (E.g. *"Break-even curve of price vs.
  utilization → 'at what utilization does this idea beat the incumbent?'"*.)
- **Tag each by cost** so the user knows what they are agreeing to:
  - **(a)** renderable from outputs the model already computes — just a new chart in
    `render()`;
  - **(b)** needs a light new computed output — a derived quantity from existing
    inputs, no new input cells;
  - **(c)** **structural** — needs new inputs, a changed functional unit, or a new
    entity — routes back to `/tea-model` (and `/tea-scope` if the scope changes).

Present it as a plain-language checklist; do not bury it in jargon.

## 3. Open-ended iteration

Close by inviting the user to steer. They can **(i)** accept some or all of your
suggestions, **(ii)** propose entirely new visualizations of their own, or **(iii)**
ask for tweaks to the model. Do not force a single choice or end the conversation.

- **Light changes — do them inline.** A new chart from existing outputs (`render()`)
  or a light new derived output that needs **no** new input cells (`compute()`).
  Keep `viz-spec.md` in sync with `render()`, re-run §1, and re-present. Editing the
  model invalidates `model_approved`, so immediately re-record it and note why in
  `decision-log.md`:

  ```
  python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
      --artifact model.py --artifact viz-spec.md
  ```

- **Structural changes — route back.** A new output requiring new inputs, a changed
  functional unit, or a different entity set is **not** a light tweak — send the
  user to `/tea-model` to revise and re-approve the model (and `/tea-scope` first if
  the scope itself changes). New input cells then need new data, so this also
  re-opens `/tea-data`.

Loop §2–§3 until the user is satisfied.

## 4. Completion

When the user signals they are done exploring, mark the run complete:

```
python scripts/orchestrator.py set-stage --run-dir RUN --stage complete
```

The `finalization -> complete` forward move is already satisfied by the
finalization quality-reviewer pass `/tea-data` recorded, so no extra spawn is
needed. The run stays **re-runnable**: invoking `/tea-insights` again re-opens it to
add or revise plots.

## Transparency in the closing message (both modes)

Fast/Auto mode especially must not be a black box. List and link the key files —
`plots/`, `model-results.json`, `final/Main Input.csv`, `Sources.csv`,
`Audit_final_consolidated.csv`, `final/run-manifest.md`, and in Auto mode
`auto-run-log.md` / `final/auto-review.md` — each with a one-line
description. Call out up front every unbacked **`U`** estimate cell (from
`final/run-manifest.md`) and every source slice recorded as **skipped-with-reason**
(from `orchestrator.py verify-spawns` / the run's `subagent_jobs`), so the user
knows exactly what to double-check before trusting a chart.

## Dependency + subagents

The model layer needs **matplotlib** (`pip install matplotlib`) for charts; the
core data pipeline stays standard-library-only. Reuse read-only subagents only as
needed (e.g. a `tea-materials-analyst` to re-read large supplied materials); the
main orchestrator serializes all canonical writes (phase scripts + orchestrator
CLI). Never include confidential material content in web queries.
