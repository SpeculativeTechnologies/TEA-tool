---
name: tea-model
description: >-
  Step 2 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data). Builds a runnable economic model
  (model.py) from the approved starting documents, dry-runs it on quick dummy
  values, agrees the visualizations with the user, and locks it behind an
  approval gate. Invoke ONLY when the user runs /tea-model or explicitly asks to
  build/model the TEA after scoping. Do not self-invoke for general TEA questions.
---

# TEA Modeling (/tea-model)

Skill 2 of three. You turn the approved `model-requirements.md` into a runnable
`model.py`, dry-run it on quick **dummy** values so the user can validate the
model's shape and its visualizations before any real data exists, then lock it
behind the `model_approved` gate and hand off to `/tea-data`. Full contract:
`references/model-building.md`.

Plain language; the user does not see schema cells or CSVs.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing.

## Gate check + startup

The CLI is the source of truth; never hand-edit state or CSVs. Run
`validate-resume`/`status` on the run:

- If `starting_documents` is **not** in `approvals.valid`, stop and tell the user
  to run `/tea-scope` first (or resume it).
- If `model_approved` is already valid, the model is **done** — point the user to
  `/tea-data`.
- Otherwise proceed (resume mid-model, or start it).

## Build, dry-run, approve

Per `references/model-building.md`:

1. `set-stage schema_setup`; build the empty working CSVs
   (`python scripts/build_csvs.py --schema "$RUN/tea-schema.json" --output-dir "$RUN"`)
   so the model has the exact `(entity, parameter)` input-cell list.
2. `set-stage model_build`; **author `runs/<project>/model.py`** from
   `templates/model.template.py`, implementing the `model-requirements.md`
   outputs/formulas. Honor the contract: a **pure function of its `--inputs` CSV**
   (reads `(entity, parameter)` values), **one figure per chosen chart** to
   `--outdir`, and a **results JSON** of the headline outputs. No hard-coded
   numbers, no network, no randomness — so the same file re-runs on real data in
   `/tea-data`. If the schema has a `BENCHMARK` entity, the template already
   **excludes it from inputs** (`load_inputs` skips it; benchmarks never enter a
   formula or the tornado) and exposes it via `load_benchmarks` — wire the
   `results["validation"]` block to compare each benchmark against the output it
   checks (per the `model-requirements.md` "Validation benchmarks" table), so the
   real run shows computed-vs-literature side by side.
3. **Quick dummy values.** Write `runs/<project>/model/dummy-inputs.csv`
   (`entity,parameter,value`) — fast, rough, order-of-magnitude numbers from your
   own knowledge. **No web search.** They exist only to validate structure, units,
   and charts.
4. **Visualizations.** Recommend a tailored chart checklist (from the outputs and
   whether it is single vs. comparison), refine it via plain chat, ask the user to
   confirm, and record `runs/<project>/viz-spec.md`
   (`templates/viz-spec.template.md`).
5. **Dry run + smoke check.** Run the model on the dummy inputs to a **separate
   dummy plot dir so the real run never overwrites them**
   (`--outdir "$RUN/plots-dummy" --tag DUMMY`), then `python scripts/check_model.py
   --model "$RUN/model.py" --inputs "$RUN/model/dummy-inputs.csv"`.
6. **Excel workbook (spreadsheet view of the outputs).** Build a viewer-friendly
   workbook so non-coders can inspect the model the way they would a hand-built
   spreadsheet — main input sheet, dashboard of headline numbers, a sheet per
   block of intermediate outputs, and the embedded charts (values only, **no
   formulas** — everything comes from the code):
   ```
   python scripts/export_workbook.py --run-dir "$RUN" --tag DUMMY
   ```
   This writes `<project>-model-workbook-DUMMY.xlsx`. Present the dummy plots,
   headline results, and the workbook — all clearly flagged as DUMMY (a structure
   check, not real numbers).
7. **Gate.** On approval:
   ```
   python scripts/orchestrator.py set-stage --run-dir RUN --stage model_review
   python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
       --artifact model.py --artifact viz-spec.md
   python scripts/orchestrator.py snapshot --run-dir RUN --label model-approved \
       --artifact model.py --artifact viz-spec.md
   ```
   Then **stop and tell the user to run `/tea-data`.** You do not gather real data
   or pick an execution mode.

## Dependency + subagents

The model layer needs **matplotlib** (`pip install matplotlib`) for charts and
**openpyxl** (`pip install openpyxl`) for the Excel workbook; the core pipeline
stays standard-library-only. Reuse read-only subagents only as needed; you
serialize all canonical writes through the CLI and phase scripts.
