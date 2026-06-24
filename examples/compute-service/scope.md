# Managed AI-Inference Service Scope

## Goal and framing

This example analyzes a hypothetical managed AI-inference service. It is the
non-industrial smoke case for the General TEA Tool: the system is organized as
cost centers rather than process units, uses CPI rather than CEPCI, has no
yield or mass-balance fields, and normalizes to a service unit rather than kg
of product.

The workflow endpoint is a populated input set that an analyst can feed into a
separate service-cost model.

## System boundary

In scope:

- Owned or reserved accelerator hardware used for first-party inference.
- Data-center power and cooling overhead.
- Network transit and load-balancing costs.
- Loaded engineering labor needed to operate the service.
- Software, observability, orchestration, and model-license costs.

Out of scope:

- Model training and research clusters.
- Sales, marketing, G&A, and corporate overhead.
- Fully on-demand spot rental economics unless explicitly used as a comparable.
- CPU-only inference and edge deployments.

## Functional unit

The functional unit is 1 million tokens served.

## Entity decomposition

| Entity | Name | Output | Description |
|---|---|---|---|
| compute_hardware | Compute hardware | Served inference | GPU or accelerator fleet running inference. |
| power_cooling | Power & cooling | Delivered kWh | Facility power draw and cooling overhead. |
| networking | Networking | Served bandwidth | Egress transit and load balancing. |
| staffing | Staffing | Operated service | ML and infrastructure engineering labor. |
| software_licensing | Software & licensing | Licensed stack | Orchestration, observability, and model-license costs. |

## Basis assumptions

| Item | Value |
|---|---|
| Currency | USD |
| Base year | 2025 |
| Inflation index | CPI |
| Geography | United States |
| Quality tags | A, B, C, D, E |

## Scenarios

This example represents one managed service configuration. Alternative hardware
or deployment models should be run as separate options under a comparison
wrapper with shared inputs where appropriate.

## Headline metrics

The downstream model is expected to calculate cost per 1M tokens served and the
cost-center contribution breakdown. This workflow stops before model execution.

## Validation targets

No validation targets are declared for this smoke example.
