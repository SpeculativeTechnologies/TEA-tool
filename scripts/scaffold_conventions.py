"""Scaffold conventions/*.csv files implied by a tea-schema.json config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Mapping

from lib.csvio import write_rows
from lib.schema import Schema, load_schema


INDEX_COLUMNS = ["year", "index", "source_note"]
CURRENCY_COLUMNS = ["from_currency", "to_currency", "year", "rate", "source_note"]
UNIT_COLUMNS = ["from_unit", "to_unit", "factor", "note"]
SCALING_COLUMNS = ["entity", "default_exponent", "target_scale", "rationale"]

PUBLIC_UNIT_CONVERSIONS = [
    {"from_unit": "Wh", "to_unit": "kWh", "factor": 0.001, "note": "1 Wh = 0.001 kWh"},
    {"from_unit": "MWh", "to_unit": "kWh", "factor": 1000, "note": "1 MWh = 1000 kWh"},
    {"from_unit": "GWh", "to_unit": "kWh", "factor": 1000000, "note": "1 GWh = 1e6 kWh"},
    {"from_unit": "kWh", "to_unit": "MJ", "factor": 3.6, "note": "1 kWh = 3.6 MJ"},
    {"from_unit": "kJ", "to_unit": "MJ", "factor": 0.001, "note": "1 kJ = 0.001 MJ"},
    {"from_unit": "GJ", "to_unit": "MJ", "factor": 1000, "note": "1 GJ = 1000 MJ"},
    {"from_unit": "Btu", "to_unit": "MJ", "factor": 0.001055, "note": "1 Btu = 0.001055 MJ"},
    {"from_unit": "MMBtu", "to_unit": "MJ", "factor": 1055, "note": "1 MMBtu = 1055 MJ"},
    {"from_unit": "Therm", "to_unit": "MJ", "factor": 105.5, "note": "1 therm ~= 105.5 MJ"},
    {"from_unit": "kcal", "to_unit": "MJ", "factor": 0.004184, "note": "1 kcal = 0.004184 MJ"},
    {"from_unit": "g", "to_unit": "kg", "factor": 0.001, "note": "1 g = 0.001 kg"},
    {"from_unit": "lb", "to_unit": "kg", "factor": 0.45359237, "note": "1 lb = 0.45359237 kg"},
    {"from_unit": "tonne", "to_unit": "kg", "factor": 1000, "note": "1 metric tonne = 1000 kg"},
    {"from_unit": "short ton", "to_unit": "tonne", "factor": 0.90718474, "note": "1 US short ton = 0.90718474 tonne"},
    {"from_unit": "long ton", "to_unit": "tonne", "factor": 1.0160469088, "note": "1 imperial long ton = 1.0160469088 tonne"},
]


def _write_if_allowed(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[Mapping[str, object]],
    *,
    force: bool,
    dry_run: bool,
) -> str:
    if path.exists() and path.stat().st_size and not force:
        return "skip (exists; use --force to overwrite)"
    if dry_run:
        return "would write"
    write_rows(path, fieldnames, rows)
    return "wrote"


def _index_rows(schema: Schema, index_name: str) -> list[dict[str, object]]:
    return [
        {
            "year": schema.base_year,
            "index": 100.0,
            "source_note": (
                f"Base-year anchor for {index_name}; extend with public annual index "
                "values before normalizing rows from other years."
            ),
        }
    ]


def _currency_rows(schema: Schema) -> list[dict[str, object]]:
    return [
        {
            "from_currency": schema.currency,
            "to_currency": schema.currency,
            "year": schema.base_year,
            "rate": 1.0,
            "source_note": "Identity rate for the schema base currency and base year.",
        }
    ]


def _scaling_rows(schema: Schema) -> list[dict[str, object]]:
    rows = []
    for entity in schema.entity_ids:
        rows.append(
            {
                "entity": entity,
                "default_exponent": "",
                "target_scale": "",
                "rationale": "Fill if CAPEX review comparisons should scale-rebase this entity.",
            }
        )
    return rows


def convention_file_plan(schema: Schema) -> dict[str, tuple[list[str], list[dict[str, object]]]]:
    plan: dict[str, tuple[list[str], list[dict[str, object]]]] = {}
    for name in schema.required_convention_files():
        if name == "currency-rates.csv":
            plan[name] = (CURRENCY_COLUMNS, _currency_rows(schema))
        elif name == "unit-conversions.csv":
            plan[name] = (UNIT_COLUMNS, PUBLIC_UNIT_CONVERSIONS)
        elif name == "scaling-exponents.csv":
            plan[name] = (SCALING_COLUMNS, _scaling_rows(schema))
        elif name in {"cepci.csv", "cpi.csv", "ppi.csv"}:
            plan[name] = (INDEX_COLUMNS, _index_rows(schema, name[:-4].upper()))
        else:
            plan[name] = (["name", "value", "source_note"], [])
    return plan


def scaffold_conventions(
    *,
    schema_path: str | Path,
    output_dir: str | Path = "conventions",
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    output_dir = Path(output_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    actions = []
    for filename, (fieldnames, rows) in convention_file_plan(schema).items():
        path = output_dir / filename
        status = _write_if_allowed(path, fieldnames, rows, force=force, dry_run=dry_run)
        actions.append((filename, path, status))
    return {"schema": schema, "output_dir": output_dir, "actions": actions, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("conventions"),
        help="Directory where convention CSVs are written",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-empty files")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args(argv)

    try:
        result = scaffold_conventions(
            schema_path=args.schema,
            output_dir=args.output_dir,
            force=args.force,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    for filename, path, status in result["actions"]:
        print(f"{prefix}{filename} -> {path}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
