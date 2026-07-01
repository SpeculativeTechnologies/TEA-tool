# Building and running the model (/tea-model)

The execution contract for `/tea-model` (Skill 2): turn the approved
`model-requirements.md` into a runnable `model.py`, dry-run it on quick dummy
values, agree the visualizations with the user, and lock it behind the
`model_approved` gate. `/tea-insights` later runs this **same file** on real data.

Keep the bookkeeping invisible: talk about "the model" and "the charts", not
schema cells and CSV columns.

## Gate check (start)

`/tea-model` only runs once `/tea-scope` is done. Read `status` and require
`starting_documents` in `approvals.valid`; otherwise stop and tell the user to run
`/tea-scope` (or resume it). Then advance the stage:

```
python scripts/orchestrator.py set-stage --run-dir RUN --stage schema_setup
```

## 1. Build the input structure

Materialize the empty working CSVs from the approved schema, so the model has the
exact `(entity, parameter)` cell list to read and the dummy file to mirror:

```
python scripts/build_csvs.py --schema "$RUN/tea-schema.json" --output-dir "$RUN"
```

This writes a skeleton `Main Input.csv` (one row per schema cell, keyed by `unit`
+ `field`). That is the file `/tea-data` will later fill with real values;
`/tea-insights` then feeds it to the same model.

## 2. Author the model

Copy the template and fill it in for this project:

```
cp templates/model.template.py "$RUN/model.py"
```

Implement `compute()`, `headline_metric()`, and `render()` from the
`model-requirements.md` outputs and formulas. The template documents and
`scripts/check_model.py` enforces the **contract**:

- **Pure function of `--inputs`.** Every number comes from the input CSV; never
  hard-code a model value. No network, no randomness, no hidden state — so
  swapping dummy → real and re-running regenerates everything identically.
- **Reads `(entity, parameter)` via `load_inputs()`.** The aliasing means one
  model reads both the quick dummy CSV (`entity,parameter,value`) and the
  pipeline's `Main Input.csv` (`unit,field,normalized_value`/`capex_usd`).
- **One figure per chosen visualization** to `--outdir`.
- **A results JSON** (`--results`) carrying the `model-requirements.md` headline
  outputs.
- **Sensitivity by internal perturbation:** `tornado()` re-calls `compute()` with
  one input swung at a time — the reason `compute()` must stay pure.
- **Benchmarks are not inputs.** If the schema declares a `BENCHMARK` entity, the
  template's `load_inputs` already skips it (so benchmarks never feed a formula or
  the tornado) and `load_benchmarks` exposes those cells. Implement the
  `model-requirements.md` "Validation benchmarks" mapping in the
  `results["validation"]` block — each researched benchmark compared against the
  computed output it checks — so `/tea-insights` can present computed-vs-literature.

For a **comparison**, read one inputs CSV per option (repeat `--inputs` or accept a
mapping) and add the option-comparison charts; keep a single project-level
`model.py`.

## 3. Dummy values (quick, no web search)

Write `runs/<project>/model/dummy-inputs.csv` with columns `entity,parameter,value`
— one row per schema cell, each a **quick, rough, order-of-magnitude** number from
your own knowledge. Do **not** web-search or build elaborate per-cell derivations;
these values exist only to validate the model's structure, units, and charts before
real data exists. Make it obvious they are placeholders (e.g. a header comment and
the `DUMMY` run tag).

## 4. Choose the visualizations

Recommend a tailored set derived from the `model-requirements.md` outputs and
whether the project is single vs. comparison; present it as a checklist, let the
user add/remove or describe changes in plain chat, incorporate the feedback, and
ask them to confirm. Record the agreed set in `runs/<project>/viz-spec.md`
(template: `templates/viz-spec.template.md`). Catalog to draw from:

| Chart | Good for | Notes |
|---|---|---|
| Cost breakdown (bar / stacked) by entity | Composition of the headline cost | Almost always useful |
| Waterfall | Additive contributions to the total | Reads well for cost build-ups |
| Tornado / one-at-a-time sensitivity | Which inputs move the headline metric | `tornado()` swings each input ±X% |
| Option-comparison bars | Comparisons only | Options on the headline + breakdown |
| Cumulative cash flow / NPV over life | DCF / time-based models only | Skip for static per-FU cost models |
| Sensitivity heatmap (1- or 2-way) | Optional deeper sensitivity | Only if the user wants it |

## 5. Dry run + smoke check

Run the model on the dummy inputs, then validate the contract. Write the dummy
figures and results to **dummy-tagged paths** (`plots-dummy/`,
`model-results-DUMMY.json`) so the real `/tea-insights` run later writes to `plots/`
and `model-results.json` **without overwriting the dummy versions** — they stay
on disk, clearly labelled, as a record of the structure check:

```
python "$RUN/model.py" --inputs "$RUN/model/dummy-inputs.csv" \
    --outdir "$RUN/plots-dummy" --results "$RUN/model-results-DUMMY.json" --tag DUMMY
python scripts/check_model.py --model "$RUN/model.py" \
    --inputs "$RUN/model/dummy-inputs.csv"
```

The `--tag DUMMY` also stamps `[DUMMY]` on every chart title, so a stray figure is
never mistaken for real data.

## 6. Excel workbook (spreadsheet view)

Every model run also produces a viewer-friendly Excel workbook so people who think
in spreadsheets rather than code or JSON can inspect the TEA. It is a **read-only
presentation layer — values only, never formulas**; all numbers are computed by
`model.py` and laid out by `scripts/export_workbook.py` (modelled on a
conventional hand-built TEA workbook):

- **Overview** — what the workbook is, data status (dummy vs. real), run details.
- **Dashboard** — the headline metrics.
- **Main Input** — the input table, with the input/value cells shaded grey.
- **One sheet per intermediate output block** the model emitted (cost breakdown,
  process groups, energy, recovery, scorecard, …) — driven generically off the
  results JSON, so a richer model produces a richer workbook.
- **Charts** — the rendered figures embedded inline.

```
python scripts/export_workbook.py --run-dir "$RUN" --tag DUMMY
```

`--run-dir` fills in the dummy defaults (`model/dummy-inputs.csv`,
`model-results-DUMMY.json`, `plots-dummy/`) and writes
`<project>-model-workbook-DUMMY.xlsx`. Present the dummy plots, the headline
results, and the workbook for review — all clearly flagged as DUMMY (structure
check, not real numbers).

To make the workbook richer, have `compute()` return intermediate tables in the
results dict (e.g. a `breakdown`, `groups`, `mass_balance`, or `cash_flow`
block); each top-level section becomes its own sheet automatically.

## 7. Model-approval gate

On approval, lock the model + chosen charts, then hand off:

```
python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
    --artifact model.py --artifact viz-spec.md
python scripts/orchestrator.py snapshot --run-dir RUN --label model-approved \
    --artifact model.py --artifact viz-spec.md
python scripts/orchestrator.py set-stage --run-dir RUN --stage model_review
```

Then direct the user to run `/tea-data`.

## Re-runs and drift

`model_approved` hashes `model.py` and `viz-spec.md`. Any later edit (e.g. a light
inline fix in `/tea-insights`) invalidates the approval until you re-`approve` it —
this is how the model never silently drifts from what the user signed off on. The
model is re-run verbatim on real data by `/tea-insights`; only `--inputs` changes.

## Dependency

The model layer needs **matplotlib** (`pip install matplotlib`) for charts and
**openpyxl** (`pip install openpyxl`) for the Excel workbook; the core data
pipeline stays standard-library-only.
