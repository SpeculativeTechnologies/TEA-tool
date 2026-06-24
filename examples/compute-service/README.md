# Worked example: Managed AI-Inference Service (scope → model → data)

This example threads all three TEA orchestrator skills end to end for a single-run
cost model (headline: **cost per 1M tokens**).

| Skill | Produces (here) |
|---|---|
| `/tea-scope` | the starting documents: [`scope.md`](scope.md), [`data-requirements.md`](data-requirements.md), [`model-requirements.md`](model-requirements.md) |
| `/tea-model` | the runnable model + its dry run: [`model.py`](model.py), [`model/dummy-inputs.csv`](model/dummy-inputs.csv), [`viz-spec.md`](viz-spec.md), and the dummy-data figures in [`plots/`](plots/) |
| `/tea-data` | (in a real run) gathers evidence into `Main Input.csv` and re-runs `model.py` on it to produce the real figures + results |

## The dummy dry run (what `/tea-model` shows you)

```
python examples/compute-service/model.py \
    --inputs examples/compute-service/model/dummy-inputs.csv \
    --outdir examples/compute-service/plots \
    --results examples/compute-service/expected/model-results.json --tag DUMMY
```

Rough dummy values (no web search) give `cost_per_1m_tokens_usd ≈ 11.82` — the
point is to validate the model's structure, units, and charts, not the number.

## The real run (what `/tea-data` does)

`/tea-data` finalizes a real `Main Input.csv` (columns `unit,field,normalized_value`)
and runs the **same** `model.py` against it — no model changes, just real inputs:

```
python examples/compute-service/model.py --inputs "<run>/Main Input.csv" \
    --outdir "<run>/plots" --results "<run>/model-results.json"
```

`model.py` reads either input shape (the dummy `entity,parameter,value` CSV or the
pipeline's `unit,field,normalized_value` CSV) via its column aliases, so the
dummy→real swap needs no edits.

## Validating the model contract

```
python scripts/check_model.py --model examples/compute-service/model.py \
    --inputs examples/compute-service/model/dummy-inputs.csv \
    --expect cost_breakdown.png --expect tornado.png
```
