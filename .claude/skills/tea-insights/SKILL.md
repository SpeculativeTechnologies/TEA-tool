---
name: tea-insights
description: >-
  Step 4 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data -> /tea-insights). Runs the approved
  model on the finalized inputs to produce the real charts and results, then
  surfaces insights and proposes new visualizations — each tied to a question
  about the user's idea — and iterates open-endedly on plots and light model
  tweaks. Invoke ONLY when the user runs /tea-insights or explicitly asks to run
  the model / explore results / suggest plots after the data is finalized. Do not
  self-invoke for general TEA questions.
---

# TEA Insights (/tea-insights)

Skill 4 of four. The data is finalized; now you **inject it into the
already-approved `model.py`, run it to produce the real charts and results, and
then help the user learn from them** — surfacing what the numbers say and
proposing new plots that answer the questions behind their idea. Execution
contract: `references/insights-and-iteration.md`; model contract:
`references/model-building.md`; pipeline authority: `workflow.md`.

Plain language; keep schemas, files, and CSVs invisible. The plots here are
**real** (model run on finalized data) — the DUMMY figures from `/tea-model` are a
separate structure check and are never overwritten.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing.

## Gate check + startup

The CLI is the source of truth; never hand-edit state or CSVs. Run
`validate-resume`/`status`:

- If `inputs_finalized` is **not** in `approvals.valid`, the data is not finalized
  yet — stop and tell the user to run `/tea-data` first (or resume it).
- If `model_approved` is **not** in `approvals.valid` (e.g. the model file was
  edited outside this skill), stop and send the user to `/tea-model` to re-approve.
- If the run is already `complete`, this skill is **re-runnable**: re-open it,
  re-present the current results, and offer to explore further (new plots or model
  tweaks). You do not need to rewind the stage to iterate.
- Otherwise proceed: run the model and present results.

## 1. Run the model on the real inputs

Run the approved model on the finalized `Main Input.csv` and build the workbook:

```
python "$RUN/model.py" --inputs "$RUN/Main Input.csv" \
    --outdir "$RUN/plots" --results "$RUN/model-results.json"
python scripts/export_workbook.py --run-dir "$RUN"
```

The real run writes to `plots/` and `model-results.json`; the dummy figures from
`/tea-model` stay in `plots-dummy/` (they are **not** overwritten). The workbook
step writes the viewer-friendly `<project>-model-workbook.xlsx` — a values-only
spreadsheet (no formulas) with the main input, a dashboard, the intermediate
outputs, and the charts, for people who prefer Excel to code.

Present the **real** plots, the headline metric(s), the charts, the workbook, and
the key sources/assumptions. **If the run has benchmarks, present the validation
comparison explicitly** — computed value vs. researched literature benchmark (with
its source) for each target, from `results["validation"]`. Flag any benchmark cell
that ended up **estimated rather than literature-sourced** (quality tag `E`/`U`):
an estimated benchmark is not an independent check, so call it out so the user does
not read it as one.

## 2. Surface insights + suggest new plots

This is the new work of this skill. Read what the model actually produced —
`model-results.json` (headline metric plus every intermediate block it emitted:
cost breakdown, tornado/sensitivity, process groups, cash flow, validation, …) and
the rendered plots — and read back **why the user is doing this**: the starting
documents (`scope.md` decision/headline metrics/scenarios/validation targets,
`model-requirements.md`, `data-requirements.md`, `process-flow.md`) **and the
materials the user originally supplied** (`provided-materials.json` plus the
registered files). For large supplied materials, fan out a read-only
`tea-materials-analyst` rather than reading them inline.

From that, name the **insights the real data surfaces** (what dominates the
headline number, what the sensitivity says moves it most, where computed vs.
benchmark agree or diverge, anything surprising relative to the user's framing or
their supplied docs), then propose a short menu (**~3–6**) of **new
visualizations**. The discipline:

- **Each suggestion is paired with the specific question about the user's idea it
  would help answer** — tie it to their decision, not to chart aesthetics
  (e.g. *"A break-even curve of price vs. utilization — answers 'at what
  utilization does this idea become cheaper than the incumbent?'"*).
- **Tag each by cost** so the user knows what they are agreeing to: (a) renderable
  from outputs the model already computes (just a new chart), (b) needs a light new
  computed output, or (c) **structural** — needs new inputs, a changed functional
  unit, or a new entity, which routes back to `/tea-model` (and `/tea-scope` if the
  scope itself changes).

Present it as a plain-language checklist.

## 3. Leave it open-ended + iterate

Close by inviting the user to steer — they can **(i)** say yes to some or all of
your suggestions, **(ii)** propose entirely new visualizations of their own, or
**(iii)** ask for tweaks to the model. Do not force a choice or end the
conversation.

For accepted suggestions, user-proposed charts, and **light** model tweaks: edit
`runs/<project>/model.py` (`render()` for a new chart from existing outputs;
`compute()` for a light new derived output that needs **no** new input cells) and
keep `runs/<project>/viz-spec.md` in sync, then re-run §1 and re-present. Editing
the model invalidates `model_approved`, so immediately re-record it and note why in
`decision-log.md`:

```
python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
    --artifact model.py --artifact viz-spec.md
```

A **structural** change (new output requiring new inputs, a changed functional
unit, a different entity set) is **not** a light tweak — send the user back to
`/tea-model` to revise and re-approve the model (and `/tea-scope` first if the
scope changes). Loop §2–§3 until the user is satisfied.

## 4. Completion

When the user signals they are done exploring, mark the run complete:

```
python scripts/orchestrator.py set-stage --run-dir RUN --stage complete
```

(The `finalization -> complete` move is already satisfied by the finalization
quality-reviewer pass `/tea-data` recorded.) The run stays **re-runnable** — the
user can invoke `/tea-insights` again later to add or revise plots.

## Transparency (both modes, especially Auto)

The final message must not be a black box. List and **link** the key files, each
with a one-line "what's in here", so the user can drill into any number:

- `plots/` and `model-results.json` — the real charts and the headline numbers.
- `<project>-model-workbook.xlsx` — the spreadsheet view of inputs, dashboard,
  intermediate outputs, and charts.
- `final/Main Input.csv` — the model inputs, one row per cell (value, units, tag).
- `Sources.csv` — every source with its URL and page/table reference.
- `Audit_final_consolidated.csv` — full provenance: every candidate value, which
  one won each cell, and why.
- `final/run-manifest.md` — coverage, quality distribution, and the **Unbacked
  Estimates (U)** list.
- In Auto mode: `auto-run-log.md` and `final/auto-review.md` — the AI's gate
  decisions, assumptions, and estimate reasoning.

Call out, in plain language and up front, anything the user should double-check:
every **`U` (unbacked) estimate** cell, and any source slice recorded as
**skipped-with-reason** (e.g. an unreadable PDF). Get the `U` cells from
`final/run-manifest.md`; get the skipped list from `orchestrator.py verify-spawns`
/ the run's `subagent_jobs`.

## Dependency + subagents

The model layer needs **matplotlib** (`pip install matplotlib`) for charts and
**openpyxl** (`pip install openpyxl`) for the Excel workbook. Reuse read-only
subagents only as needed (e.g. a `tea-materials-analyst` to re-read large supplied
materials); you serialize all canonical writes through the CLI and phase scripts.
