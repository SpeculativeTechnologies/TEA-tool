<!--
viz-spec.md — written by /tea-model, approved by the user (part of model_approved).

Records the visualizations the user agreed to for this run. model.py renders one
figure per row into runs/<project>/plots/. Keep this in sync with render() in
model.py: every chart listed here must be produced, and every produced figure
should be listed here.
-->

# Visualization spec — [Display Name]

- **Headline metric:** [name + units, e.g. `cost per 1M tokens (USD)`]
- **Inputs:** `model/dummy-inputs.csv` (dry run) → `Main Input.csv` (real run)
- **Sensitivity swing:** [tornado ± %, e.g. ±20%]

## Chosen charts

| Chart | File (in `plots/`) | What it shows | Notes |
|---|---|---|---|
| [Cost breakdown by entity] | `cost_breakdown.png` | [headline cost composition] | [always-on] |
| [Tornado] | `tornado.png` | [headline sensitivity to each input] | [±20%] |
| [...] | `[file].png` | [...] | [...] |

## Not included

- [Charts considered and dropped, and why — keeps the approved scope explicit.]
