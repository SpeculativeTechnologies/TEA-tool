<!--
model-requirements.md — written by /tea-scope, not the analyst.

This is a canonical starting document, alongside scope.md, process-flow.md, and
data-requirements.md. It is the SPECIFICATION that /tea-model implements as a
runnable model.py: the outputs to compute, their formulas, and the schema cells
each output consumes. The concise human review companion is scope-summary.md.
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
inputs into the headline number — not just trust a black box. Anchor it to the
**connected entities** in `process-flow.md`: the cost flows along that chain to the
functional-unit result. Two parts:

**1. Solve order, walking the entity graph.** Trace the chain end to end, naming the
entities so the words line up with the process-flow diagram:

[e.g. "Start at each entity's inputs. For every entity, its contribution is computed
from its own parameters — a price × a quantity, an energy intensity × an energy
price, or a CapEx annualized over its life. Walk the entities in flow order (Feed
prep → Reactor → Separation → Finishing), carrying each entity's output to the next.
Shared reference values (electricity price, loaded labor rate) are read once from
`REF` and reused wherever they apply. The per-entity contributions are then
**aggregated** and **divided by the functional unit** so everything is expressed per
`1,000 lamp-hours` (or `$/kg`, `$/area`). That per-functional-unit total is the
headline number; the sensitivity chart re-runs this whole chain while swinging one
input at a time."]

**2. Worked example — one full path to the headline.** Carry a single representative
input **all the way through** to the headline figure: through its entity, then
aggregation and normalization to the per-functional-unit number — not an isolated
line item. **Prefer a value the user already supplied** (fixed input); otherwise use
round, **clearly-labeled illustrative numbers** — never a researched or benchmark
value.

> *Illustrative only — real values are gathered in the data step.*
>
> [e.g. "Follow electricity through the Reactor entity. If the Reactor draws
> **2 kWh per kg** of its output and electricity costs **\$0.12/kWh**, its
> electricity contribution is 2 × \$0.12 = **\$0.24/kg**. That joins the Reactor's
> other line items (feedstock, CapEx annualized) to give the Reactor's
> **\$X/kg**; adding the other entities' per-kg contributions and normalizing to the
> functional unit yields the headline **\$Y/kg**. The model does exactly this for
> every entity in the flow and sums to the functional-unit total."]

The point is the *method* — how a single input propagates through its entity and the
aggregation to become part of the headline number. State plainly that the figures are
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

## Handoff to /tea-model, /tea-data, and /tea-insights

This document defines the model. `/tea-model` builds `model.py` from the outputs and
formulas above and dry-runs it on dummy values; `/tea-data` finalizes one finite
numeric value per schema cell; `/tea-insights` runs the same `model.py` on those
finalized inputs to produce the figures and results.
