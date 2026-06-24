<!--
model-requirements.md — written by /tea-scope, not the analyst.

This is the third starting document (alongside scope.md and data-requirements.md).
It is the SPECIFICATION that /tea-model implements as a runnable model.py: the
outputs to compute, their formulas, and the schema cells each output consumes.
Make it explicit and numeric.

Keep every row's "required inputs" pointing at real schema cells
(entity + parameter) so Stage 0 can confirm the parameter catalog covers every
output. Text, categories, and structured context belong here and in scope.md —
never as numeric model-input cells.

Replace each bracketed prompt. Delete sections that do not apply.
-->

# Model Requirements — [Display Name]

- **TEA id:** `[tea-id]`
- **Project type:** [single run | comparison of N options]
- **Functional unit:** [e.g. `1,000 lamp-hours at ~800 lumens`]
- **Basis:** [currency], [base year], [inflation index], [geography]

## Desired outputs

What the downstream model is expected to compute. One row per headline output.

| Output | Units | Per functional unit? | Description |
|---|---|---|---|
| [e.g. electricity cost] | [USD / 1,000 lamp-h] | [yes/no] | [what it represents] |
| [e.g. replacement cost] | [USD / 1,000 lamp-h] | [yes/no] | [...] |
| [e.g. total operating cost] | [USD / 1,000 lamp-h] | [yes/no] | [...] |

## Functional-unit relationship

How each output is expressed per the functional unit (the denominator everything
normalizes to). State any conversion the model applies between entity outputs and
the functional unit.

[e.g. "Electricity cost per 1,000 lamp-hours = rated_wattage (W) × 1,000 h ÷ 1000
× electricity_price (USD/kWh)." Spell out the chain so each input is traceable.]

## Inputs required by each output

Every input each output consumes, mapped to its schema cell. Each cell must be a
numeric parameter in `tea-schema.json`.

| Output | Required input (entity, parameter) | Supplied or still needed | Notes |
|---|---|---|---|
| [electricity cost] | (electricity_use, rated_wattage) | [supplied/needed] | [source or gap] |
| [electricity cost] | (REF, electricity_price) | [supplied/needed] | [shared reference] |
| [replacement cost] | (lamp, lamp_lifetime) | [needed] | [...] |
| [replacement cost] | (lamp, bulb_price) | [needed] | [...] |

## Supplied vs. still-needed inputs

- **Supplied / fixed inputs:** [list the cells the analyst provided, and which are
  fixed (authoritative) vs. candidate evidence — these live in `user-inputs.csv`].
- **Still needed:** [cells the pipeline must research, extract, or estimate].

## Intended formulas / calculation logic

The calculation logic the model applies. `/tea-model` implements this in `model.py`
(reading the schema cells above), so keep it explicit enough to implement faithfully.

```
[e.g.
electricity_cost_per_fu = rated_wattage_kW * fu_hours * electricity_price
replacement_cost_per_fu = (fu_hours / lamp_lifetime) * bulb_price
total_operating_cost_per_fu = electricity_cost_per_fu + replacement_cost_per_fu
]
```

## Scenarios and comparison relationships

- **Scenarios:** [materially different scenarios kept as separate runs, not
  collapsed — or "none"].
- **Comparison:** [for comparisons: the options, the shared functional unit, and
  the shared inputs (e.g. `REF,electricity_price`) that must be equivalent across
  options — or "single run, no comparison"].

## Modeling assumptions and unresolved dependencies

- [Assumptions the model relies on that are not themselves model inputs, e.g.
  operating hours per year, discount rate, utilization.]
- [Unresolved dependencies or open questions that affect which inputs are needed.]

## Handoff to /tea-model and /tea-data

This document defines the model. `/tea-model` builds `model.py` from the outputs and
formulas above and dry-runs it on dummy values; `/tea-data` finalizes one finite
numeric value per schema cell and runs the same `model.py` to produce the figures
and results.
