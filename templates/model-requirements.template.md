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

## How the model is solved (plain-language walkthrough)

A non-expert should be able to read this and understand *how* their model turns
inputs into the headline numbers — not just trust a black box. Two parts:

**1. Solve order, in words.** Walk the chain end to end:

[e.g. "Each process unit's cost is computed from its own inputs (a price × a
quantity, or a CapEx annualized over its life). Per-unit costs are then summed and
divided by the functional unit so everything is expressed per `1,000 lamp-hours`.
Shared values (electricity price, labor rate) are read once and reused across
units. The headline metric is the total cost per functional unit; the sensitivity
chart re-runs this whole chain while swinging one input at a time."]

**2. Worked example of one representative subcomponent.** Pick the subcomponent
that best conveys the mechanics and carry it end to end with real arithmetic.
**Prefer a value the user already supplied** (fixed input); otherwise use round,
**clearly-labeled illustrative numbers** — never a researched or benchmark value.

> *Illustrative only — real values are gathered in the data step.*
>
> [e.g. "Take the electricity-cost line. If the rated draw were **10 W** and
> electricity cost **\$0.12/kWh**, then over **1,000 lamp-hours**:
> 10 W × 1,000 h ÷ 1,000 = **10 kWh**, × \$0.12 = **\$1.20 per 1,000 lamp-hours**.
> The model does exactly this for each unit and sums the results."]

The point is the *method*, not the number — state plainly that the figures are
illustrative (or user-supplied), and that the data step replaces them.

## Validation benchmarks

External benchmarks the results are checked against. **Metric and unit are named
here; values are researched in `/tea-data`, not assumed.** Each becomes a cell
under the reserved `BENCHMARK` entity — collected and audited like any other cell,
but **ignored by the model as an input** and instead displayed beside the matching
computed output (computed X vs. literature Y [source]).

| Benchmark metric | Unit | Compared against which output | Value |
|---|---|---|---|
| [e.g. literature billet cost] | [USD/kg] | [total_cost_per_fu] | _researched in data step_ |

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
