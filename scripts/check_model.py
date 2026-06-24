#!/usr/bin/env python3
"""Smoke + convention check for a run's bespoke ``model.py`` (/tea-model).

Confirms the model honors the contract in ``references/model-building.md`` so the
same file can be re-run on real data by ``/tea-data``:

- runs headless on a given inputs CSV and exits 0,
- writes a results JSON with a non-empty ``headline`` block,
- writes at least one figure to ``--outdir`` (or exactly the ``--expect`` files).

Used by ``/tea-model`` before the ``model_approved`` gate and by the test suite.

    python scripts/check_model.py --model runs/<proj>/model.py \
        --inputs runs/<proj>/model/dummy-inputs.csv [--expect cost_breakdown.png ...]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def check_model(
    model_path: str | Path,
    inputs_path: str | Path,
    *,
    expect: list[str] | None = None,
    outdir: str | Path | None = None,
) -> dict:
    """Run ``model_path`` against ``inputs_path`` and validate the contract."""

    model_path = Path(model_path)
    inputs_path = Path(inputs_path)
    problems: list[str] = []
    if not model_path.exists():
        return {"ok": False, "problems": [f"model not found: {model_path}"]}
    if not inputs_path.exists():
        return {"ok": False, "problems": [f"inputs not found: {inputs_path}"]}

    tmp_ctx = tempfile.TemporaryDirectory() if outdir is None else None
    out = Path(outdir) if outdir is not None else Path(tmp_ctx.name)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "model-results.json"

    try:
        proc = subprocess.run(
            [sys.executable, str(model_path),
             "--inputs", str(inputs_path),
             "--outdir", str(out),
             "--results", str(results_path),
             "--tag", "CHECK"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            problems.append(f"model exited {proc.returncode}: {proc.stderr.strip()[:500]}")

        results: dict = {}
        if not results_path.exists():
            problems.append(f"no results JSON at {results_path}")
        else:
            try:
                results = json.loads(results_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"results JSON invalid: {exc}")
            if not results.get("headline"):
                problems.append("results JSON has no non-empty 'headline' block")

        written = sorted(p.name for p in out.glob("*.png"))
        if expect:
            missing = [name for name in expect if not (out / name).exists()]
            if missing:
                problems.append(f"expected plot(s) missing: {missing}")
        elif not written:
            problems.append("model wrote no .png figures to --outdir")
        for name in written:
            if (out / name).stat().st_size == 0:
                problems.append(f"empty figure: {name}")

        return {
            "ok": not problems,
            "model": str(model_path).replace("\\", "/"),
            "headline": results.get("headline", {}),
            "plots": written,
            "problems": problems,
        }
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--expect", action="append", default=[],
                    help="expected plot filename (repeatable); default: require >=1 png")
    ap.add_argument("--outdir", default=None, help="plot dir (default: a temp dir)")
    args = ap.parse_args(argv)

    summary = check_model(args.model, args.inputs, expect=args.expect or None, outdir=args.outdir)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
