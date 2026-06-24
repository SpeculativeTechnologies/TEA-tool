# Model Requirements — Managed AI-Inference Service

- **TEA id:** `compute-service`
- **Project type:** single run
- **Functional unit:** 1M tokens served
- **Basis:** USD, 2025, CPI, United States

## Desired outputs

| Output | Units | Per functional unit? | Description |
|---|---|---|---|
| Cost per 1M tokens | USD / 1M tokens | yes | Headline blended cost to serve 1M tokens. |
| Cost-center breakdown | USD / 1M tokens | yes | Contribution of each cost center to the headline. |

## Functional-unit relationship

Each cost center reports an amortized `monthly_cost` (USD/month). The served
volume per month is set by the inference fleet's throughput:

```
served_Mtokens_per_month = throughput(compute_hardware) [1M tokens/hr] * HOURS_PER_MONTH
cost_per_1M_tokens(center) = monthly_cost(center) / served_Mtokens_per_month
cost_per_1M_tokens(total)  = sum over centers of cost_per_1M_tokens(center)
```

`HOURS_PER_MONTH = 730` is a calendar unit-conversion constant, not a tunable
model value. `throughput` is the realized (utilization-adjusted) serving rate, so
no separate utilization factor is needed.

## Inputs required by each output

Every input maps to a numeric `tea-schema.json` cell.

| Output | Required input (entity, parameter) | Supplied or still needed | Notes |
|---|---|---|---|
| Cost per 1M tokens | (compute_hardware, monthly_cost) | needed | amortized GPU fleet cost |
| Cost per 1M tokens | (power_cooling, monthly_cost) | needed | facility power + cooling |
| Cost per 1M tokens | (networking, monthly_cost) | needed | egress + load balancing |
| Cost per 1M tokens | (staffing, monthly_cost) | needed | loaded engineering labor |
| Cost per 1M tokens | (software_licensing, monthly_cost) | needed | orchestration/observability/licenses |
| Cost per 1M tokens | (compute_hardware, throughput) | needed | realized 1M tokens/hr |

## Supplied vs. still-needed inputs

- **Supplied / fixed inputs:** none for the smoke example.
- **Still needed:** the six cells above. The remaining schema cells
  (`power_draw` on compute_hardware/power_cooling and the `REF` prices —
  `industrial_electricity_price`, `gpu_street_price`, `transit_bandwidth_price`,
  `ml_engineer_loaded_rate`) are **supporting** inputs used during data acquisition
  to derive and sanity-check each center's `monthly_cost`; the headline `model.py`
  consumes the six cells above.

## Intended formulas / calculation logic

```
served = throughput_compute_hardware * 730
total_cost_per_1M = sum(monthly_cost[c] / served for c in cost_centers)
```

## Scenarios and comparison relationships

- **Scenarios:** one managed-service configuration; alternatives would be separate
  options under a comparison wrapper.
- **Comparison:** single run, no comparison.

## Modeling assumptions and unresolved dependencies

- `HOURS_PER_MONTH = 730` (calendar constant).
- `throughput` is the realized serving rate, already net of utilization.
- Each center's `monthly_cost` is taken as the model input; the `power_draw` and
  `REF` price cells support its derivation during data acquisition rather than
  entering the headline formula directly.
