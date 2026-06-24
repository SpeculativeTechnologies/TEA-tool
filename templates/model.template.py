#!/usr/bin/env python3
"""Bespoke TEA model for <PROJECT> — authored by /tea-model.

This is a per-run template. `/tea-model` copies it to `runs/<project>/model.py`
and fills in `compute()`, `headline_metric()`, and `render()` from the project's
`model-requirements.md`. Keep these rules — `scripts/check_model.py` enforces
them and `/tea-data` re-runs this exact file on real data:

- **Pure function of the input CSV.** Every number comes from `--inputs`; never
  hard-code a model value here. Swapping the input CSV (dummy -> real) and
  re-running must regenerate everything. No network, no randomness, no hidden
  state.
- **One figure per chosen visualization** written to `--outdir` (see the run's
  `viz-spec.md`).
- **A results JSON** with the `model-requirements.md` headline outputs.

Usage:
    python model.py [--inputs CSV] [--outdir DIR] [--results JSON] [--tag TEXT]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: never opens a window
import matplotlib.pyplot as plt  # noqa: E402


# --- input layer -----------------------------------------------------------
# Column aliases so the SAME model reads a quick dummy CSV (entity,parameter,value)
# and the pipeline's Main Input.csv (unit,field,normalized_value/capex_usd).
ENTITY_KEYS = ("entity", "unit")
PARAM_KEYS = ("parameter", "field")
VALUE_KEYS = ("value", "capex_usd", "normalized_value")


def _first(row: dict, keys: tuple[str, ...]):
    for key in keys:
        val = row.get(key)
        if val not in (None, ""):
            return val
    return None


def load_inputs(path: str | Path) -> dict[tuple[str, str], float]:
    """Return {(entity, parameter): float}. Non-numeric cells are skipped."""

    inputs: dict[tuple[str, str], float] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entity = _first(row, ENTITY_KEYS)
            parameter = _first(row, PARAM_KEYS)
            raw = _first(row, VALUE_KEYS)
            if entity is None or parameter is None or raw is None:
                continue
            try:
                inputs[(entity.strip(), parameter.strip())] = float(str(raw).replace(",", ""))
            except ValueError:
                continue  # JSON/text cell, header artifact, etc.
    return inputs


def get(inputs: dict, entity: str, parameter: str, default: float = float("nan")) -> float:
    return inputs.get((entity, parameter), default)


# --- model -----------------------------------------------------------------
def compute(inputs: dict[tuple[str, str], float]) -> dict:
    """Compute the model-requirements outputs. REPLACE with the project formulas.

    Must be a pure function of `inputs` (sensitivity analysis re-calls it with
    perturbed inputs). Return at least {"headline": {...}, "breakdown": {...}}.

    Scaffold below: treat every `*, cost_per_fu` cell as one entity's
    contribution and sum them into the headline total.
    """

    breakdown = {
        entity: value
        for (entity, parameter), value in inputs.items()
        if parameter == "cost_per_fu"
    }
    total = sum(v for v in breakdown.values() if v == v)  # NaN-safe
    return {"headline": {"total_cost_per_fu": total}, "breakdown": breakdown}


# --- sensitivity ------------------------------------------------------------
def headline_metric(inputs: dict) -> float:
    """The single number the tornado chart swings. REPLACE if renamed."""

    return compute(inputs)["headline"].get("total_cost_per_fu", float("nan"))


def tornado(inputs: dict, pct: float = 0.2) -> tuple[float, list[tuple[str, str, float]]]:
    """One-at-a-time +/- pct swing of each input on the headline metric.

    Self-contained sensitivity: re-runs `compute()` with one cell perturbed at a
    time. This is why the model must be a pure function of `inputs`.
    """

    base = headline_metric(inputs)
    swings: list[tuple[str, str, float]] = []
    for key, value in inputs.items():
        low = dict(inputs)
        low[key] = value * (1 - pct)
        high = dict(inputs)
        high[key] = value * (1 + pct)
        label = f"{key[0]}.{key[1]}"
        swings.append((label, "low", headline_metric(low)))
        swings.append((label, "high", headline_metric(high)))
    return base, swings


# --- visualizations ---------------------------------------------------------
def render(inputs: dict, results: dict, outdir: str | Path, tag: str = "") -> list[str]:
    """Write one PNG per chosen visualization (see viz-spec.md). REPLACE/extend
    with the approved chart set. The scaffold draws a cost-breakdown bar."""

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = f"  [{tag}]" if tag else ""
    written: list[str] = []

    breakdown = results.get("breakdown") or {}
    if breakdown:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(list(breakdown.keys()), list(breakdown.values()), color="#3b6ea5")
        ax.set_title("Cost breakdown by entity" + suffix)
        ax.set_ylabel("cost / functional unit")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        fig.tight_layout()
        path = outdir / "cost_breakdown.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written.append(str(path).replace("\\", "/"))

    return written


# --- entrypoint -------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inputs", default="Main Input.csv")
    ap.add_argument("--outdir", default="plots")
    ap.add_argument("--results", default=None,
                    help="results JSON path (default: <outdir>/../model-results.json)")
    ap.add_argument("--tag", default="", help="label stamped on titles + results (e.g. DUMMY)")
    args = ap.parse_args(argv)

    inputs = load_inputs(args.inputs)
    results = compute(inputs)
    results["tag"] = args.tag
    results["inputs_path"] = str(args.inputs).replace("\\", "/")
    results["plots"] = render(inputs, results, args.outdir, tag=args.tag)

    results_path = Path(args.results) if args.results else Path(args.outdir).parent / "model-results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(
        {"headline": results["headline"], "plots": results["plots"],
         "results": str(results_path).replace("\\", "/"), "tag": args.tag},
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
