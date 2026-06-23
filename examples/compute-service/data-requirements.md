# Managed AI-Inference Service Data Requirements

## Entities

| ID | Display name | Output | Scope frame | Known out of scope | Estimation policy |
|---|---|---|---|---|---|
| compute_hardware | Compute hardware | Served inference | Owned or reserved GPU accelerators amortized over their service life, running first-party inference. | On-demand spot rental, training clusters, CPU-only inference. | first_principles_only |
| power_cooling | Power & cooling | Delivered kWh | Grid electricity plus cooling overhead for the inference fleet at a colocation facility. | On-site generation, free-air-cooled edge sites. | first_principles_only |
| networking | Networking | Served bandwidth | Egress transit bandwidth and load balancing for the served API. | Private interconnect, dedicated fiber, CDN-cached static delivery. | first_principles_only |
| staffing | Staffing | Operated service | Loaded ML and infrastructure engineering labor to operate and maintain the inference service. | Model research, training staff, sales, G&A. | first_principles_only |
| software_licensing | Software & licensing | Licensed stack | Per-seat or per-usage licensing for orchestration, observability, and model licenses. | Fully open-source self-hosted stack with no license cost. | first_principles_only |

## Parameter catalog

| Parameter ID | Label | Rule type | Applies to | First class | Notes |
|---|---|---|---|---|---|
| monthly_cost | Monthly cost | MONETARY | all | true | Amortized monthly cost for the cost center. |
| power_draw | Power draw | INTENSITY | compute_hardware, power_cooling | true | kWh per 1M tokens. |
| throughput | Throughput | RATE | compute_hardware | false | 1M tokens per hour. |
| notes | Notes | TEXT | all | false | Free-text support notes. |

## Reference values

These values are searched context-free and carried under `REF`.

| Parameter ID | Label | Rule type | Canonical unit | Market basis |
|---|---|---|---|---|
| industrial_electricity_price | Industrial electricity price | MONETARY | USD/kWh | US industrial bulk |
| gpu_street_price | GPU street price | MONETARY | USD/unit | Data-center GPU street price |
| transit_bandwidth_price | Transit bandwidth price | MONETARY | USD/Mbps/mo | IP transit at a major exchange |
| ml_engineer_loaded_rate | ML engineer loaded rate | MONETARY | USD/hr | US loaded labor cost |

## Applicability

Reference values apply only to `REF`. `monthly_cost` and `notes` apply to all
real cost centers. `power_draw` applies only to compute hardware and
power/cooling. `throughput` applies only to compute hardware.

## Estimation

All entities are `first_principles_only` for the smoke example. No comparable
rubric is required.

## Quality tags

Use A, B, C, D, and E. E is reserved for estimates. Analyst overrides of held
estimates are re-tagged to D.

## Conventions needed

- inflation_index:CPI
- currency_rates
- unit_conversions

