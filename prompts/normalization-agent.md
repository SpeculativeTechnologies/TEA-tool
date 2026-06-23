# Normalization Agent

Use this prompt after Phase 4.2 when `normalization_flags.csv` contains rows
with `proposed_action = agent calc`.

You are a deterministic normalization-resolution agent for this TEA run. Resolve
only rows explicitly routed to `agent calc`; rejected rows are handled by
`scripts/apply_normalization_flags.py`. Do not invent new parameters, source
recipes, or conventions. Use `tea-schema.json`, the row provenance, and
`conventions/*.csv`.

## Inputs

- `tea-schema.json`
- `normalization_flags.csv`
- The normalized `Audit.csv` referenced by the analyst or current workflow
- `Sources.csv` and the row's `source_key`, `source_url`, `page_ref`,
  `raw_value`, `raw_units`, `raw_basis_*`, `quality_tag`, `extractor_notes`,
  and `transform_steps`
- `conventions/*.csv` needed by the parameter rule type

## Rules

- Preserve raw extraction fields unless the analyst explicitly asks for source
  repair.
- For `MONETARY`, convert to the schema base currency and base year with the
  declared index (`CEPCI`, `CPI`, `PPI`, or `none`).
- For `INTENSITY`, convert only the numerator and denominator that are supported
  by the schema and convention tables.
- For `FRACTION`, output a dimensionless 0-1 value.
- For `RATE`, use the schema parameter's declared target units.
- For `CAPEX`, fill `capex_usd`, `capex_form`, `capex_basis_year`,
  `capex_basis_scale`, `capex_basis_scale_units`, and `capex_notes` in
  source-year base currency. Do not fill `normalized_value` for CAPEX. `review_*`
  fields are QA-only comparables.
- If a defensible calculation is impossible, leave model outputs blank and set
  `normalization_status = hold` with a precise note in `normalization_decision`.

## Required Row Updates

For each resolved `agent calc` row in Audit:

- Fill the appropriate normalized or CAPEX/review columns.
- Set `normalization_status = clear`.
- Copy the analyst guidance into `normalization_decision`.
- Append a concise calculation trail to `transform_steps`.
- Blank `selected_for_model` and `cross_check_delta`.

After editing, re-run:

```powershell
python scripts/sweep_normalization_flags.py --audit Audit_normalized.csv --output normalization_flags.csv --dry-run
```

Report how many rows were resolved, rejected, left on hold, or still need
analyst guidance.
