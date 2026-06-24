# Visualization spec — Managed AI-Inference Service

- **Headline metric:** cost per 1M tokens (USD / 1M tokens)
- **Inputs:** `model/dummy-inputs.csv` (dry run) → `Main Input.csv` (real run)
- **Sensitivity swing:** tornado ±20%

## Chosen charts

| Chart | File (in `plots/`) | What it shows | Notes |
|---|---|---|---|
| Cost breakdown by cost center | `cost_breakdown.png` | Each center's USD / 1M tokens contribution | Always-on composition view |
| Tornado | `tornado.png` | Headline sensitivity to each consumed input | ±20% one-at-a-time |

## Not included

- Cumulative cash flow / NPV — this is a static per-functional-unit cost model
  with no project timeline, so a time-based chart would be empty.
