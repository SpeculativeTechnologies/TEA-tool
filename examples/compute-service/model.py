#!/usr/bin/env python3
"""Managed AI-Inference Service — cost per 1M tokens. Authored by /tea-model.

Worked example of the /tea-model output: a bespoke, runnable model that is a pure
function of its `--inputs` CSV (reads (entity, parameter) values), writes one
figure per chosen visualization to `--outdir`, and emits a results JSON. The same
file runs on the quick dummy CSV (/tea-model) and on the pipeline's real
Main Input.csv (/tea-insights).

    python model.py [--inputs CSV] [--outdir DIR] [--results JSON] [--tag TEXT]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Calendar unit-conversion constant (NOT a tunable model value). See
# model-requirements.md: throughput is the realized, utilization-adjusted rate.
HOURS_PER_MONTH = 730.0

COST_CENTERS = ("compute_hardware", "power_cooling", "networking", "staffing", "software_licensing")

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
    inputs: dict[tuple[str, str], float] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entity, parameter, raw = _first(row, ENTITY_KEYS), _first(row, PARAM_KEYS), _first(row, VALUE_KEYS)
            if entity is None or parameter is None or raw is None:
                continue
            try:
                inputs[(entity.strip(), parameter.strip())] = float(str(raw).replace(",", ""))
            except ValueError:
                continue
    return inputs


def get(inputs: dict, entity: str, parameter: str, default: float = float("nan")) -> float:
    return inputs.get((entity, parameter), default)


def compute(inputs: dict[tuple[str, str], float]) -> dict:
    served = get(inputs, "compute_hardware", "throughput") * HOURS_PER_MONTH  # 1M-token units / month
    breakdown = {c: get(inputs, c, "monthly_cost") / served for c in COST_CENTERS}
    total = sum(v for v in breakdown.values() if v == v)  # NaN-safe
    return {
        "headline": {"cost_per_1m_tokens_usd": total, "served_mtokens_per_month": served},
        "breakdown": breakdown,
    }


def headline_metric(inputs: dict) -> float:
    return compute(inputs)["headline"]["cost_per_1m_tokens_usd"]


def tornado(inputs: dict, pct: float = 0.2) -> tuple[float, list[tuple[str, float, float]]]:
    """One-at-a-time ±pct swing of each consumed input on the headline metric."""

    consumed = [("compute_hardware", "throughput")] + [(c, "monthly_cost") for c in COST_CENTERS]
    base = headline_metric(inputs)
    rows: list[tuple[str, float, float]] = []
    for key in consumed:
        if key not in inputs:
            continue
        lo_inputs = dict(inputs)
        lo_inputs[key] = inputs[key] * (1 - pct)
        hi_inputs = dict(inputs)
        hi_inputs[key] = inputs[key] * (1 + pct)
        rows.append((f"{key[0]}.{key[1]}", headline_metric(lo_inputs), headline_metric(hi_inputs)))
    rows.sort(key=lambda r: abs(r[2] - r[1]), reverse=True)
    return base, rows


def render(inputs: dict, results: dict, outdir: str | Path, tag: str = "") -> list[str]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = f"  [{tag}]" if tag else ""
    written: list[str] = []

    # Cost breakdown by cost center.
    breakdown = results["breakdown"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(list(breakdown.keys()), list(breakdown.values()), color="#3b6ea5")
    ax.set_title("Cost per 1M tokens by cost center" + suffix)
    ax.set_ylabel("USD / 1M tokens")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    p = outdir / "cost_breakdown.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    written.append(str(p).replace("\\", "/"))

    # Tornado: headline sensitivity to each input (±20%).
    base, rows = tornado(inputs)
    if rows:
        labels = [r[0] for r in rows]
        ypos = range(len(rows))
        fig, ax = plt.subplots(figsize=(7, 4))
        for y, (_, lo, hi) in zip(ypos, rows):
            ax.barh(y, hi - lo, left=min(lo, hi), color="#c0794a")
        ax.axvline(base, color="#333", linestyle="--", linewidth=1, label=f"base = {base:.2f}")
        ax.set_yticks(list(ypos))
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("USD / 1M tokens")
        ax.set_title("Sensitivity of cost per 1M tokens (±20%)" + suffix)
        ax.legend(loc="lower right")
        fig.tight_layout()
        p = outdir / "tornado.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        written.append(str(p).replace("\\", "/"))

    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inputs", default="Main Input.csv")
    ap.add_argument("--outdir", default="plots")
    ap.add_argument("--results", default=None)
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)

    inputs = load_inputs(args.inputs)
    results = compute(inputs)
    results["tag"] = args.tag
    results["inputs_path"] = str(args.inputs).replace("\\", "/")
    results["plots"] = render(inputs, results, args.outdir, tag=args.tag)

    results_path = Path(args.results) if args.results else Path(args.outdir).parent / "model-results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"headline": results["headline"], "plots": results["plots"],
                      "results": str(results_path).replace("\\", "/"), "tag": args.tag}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
