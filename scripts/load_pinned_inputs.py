"""Load pinned-inputs.csv into Audit.csv and Main Input.csv.

Pinned inputs are analyst-authored, per-cell carry-forward values. The loader
validates each cell against ``tea-schema.json``, writes them as Audit rows with
``relevance_status=pinned``, and marks the matching Main Input skeleton cells
with ``pinned=TRUE`` so downstream lanes skip them.

Examples:
    python scripts/load_pinned_inputs.py --schema runs/run-2/tea-schema.json --run-dir runs/run-2
    python scripts/load_pinned_inputs.py --schema tea-schema.json --pinned pinned-inputs.csv --audit Audit.csv --main-input "Main Input.csv"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import (
    AUDIT_FIELDNAMES,
    MAIN_INPUT_FIELDNAMES,
    PINNED_INPUTS_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from lib.pinned import PINNED_STATUS, cell_key, is_pinned_row, validate_cell
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema
from lib.source_url import source_url_for


OPTIONAL_INPUT_COLUMNS = {
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "page_ref",
    "quality_tag",
    "notes",
}
REQUIRED_INPUT_COLUMNS = [
    name for name in PINNED_INPUTS_FIELDNAMES if name not in OPTIONAL_INPUT_COLUMNS
]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _row_has_content(row: Mapping[str, object]) -> bool:
    return any(_clean(value) for value in row.values())


def _validate_unique_cells(rows: list[dict[str, str]]) -> None:
    seen: dict[tuple[str, str], int] = {}
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        key = cell_key(row)
        if not any(key):
            continue
        if key in seen:
            errors.append(
                f"row {idx}: duplicate pinned cell ({key[0]},{key[1]}); "
                f"first seen on row {seen[key]}"
            )
        else:
            seen[key] = idx
    if errors:
        raise ValueError("\n".join(errors))


def _source_url(row: Mapping[str, object], sources_path: Path | None) -> str:
    url = _clean(row.get("source_url"))
    if url:
        return url
    source_key = _clean(row.get("source_key"))
    if not source_key:
        return ""
    if sources_path is not None:
        url = source_url_for(source_key, sources_path, required=False)
    return url


def pinned_to_audit_row(
    row: Mapping[str, object],
    *,
    sources_path: Path | None = None,
) -> dict[str, str]:
    """Project one pinned-input row into the Audit.csv schema."""

    out = blank_row(AUDIT_FIELDNAMES)
    for key in (
        "entity",
        "parameter",
        "raw_value",
        "raw_units",
        "raw_basis_scale",
        "raw_basis_scale_units",
        "raw_basis_year",
        "source_key",
        "page_ref",
        "quality_tag",
        "notes",
    ):
        out[key] = _clean(row.get(key))
    out["source_url"] = _source_url(row, sources_path)
    out["relevance_status"] = PINNED_STATUS
    if not out["page_ref"]:
        out["page_ref"] = "pinned-inputs.csv"
    note = out["notes"]
    out["notes"] = "pinned input" if not note else f"pinned input: {note}"
    return out


def _validate_pinned_rows(
    rows: list[dict[str, str]],
    schema: Schema,
    *,
    sources_path: Path | None,
) -> None:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        where = f"pinned-inputs.csv row {idx}"
        entity, parameter = cell_key(row)
        try:
            validate_cell(schema, entity, parameter, row_label=where)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for key in ("raw_value", "raw_units", "source_key"):
            if not _clean(row.get(key)):
                errors.append(f"{where}: {key} is required")
        if not _source_url(row, sources_path):
            errors.append(f"{where}: source_url is required or must resolve from Sources.csv")
        tag = _clean(row.get("quality_tag")).upper()
        if tag and tag not in {str(item).upper() for item in schema.quality_tags}:
            errors.append(f"{where}: quality_tag {tag!r} is not one of {schema.quality_tags!r}")
    if errors:
        raise ValueError("\n".join(errors))


def _main_input_skeleton_rows(schema: Schema) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entity_id, parameter_id in schema.skeleton_cells():
        row = blank_row(MAIN_INPUT_FIELDNAMES)
        row["entity"] = entity_id
        row["parameter"] = parameter_id
        row["notes"] = (
            "no reference value - context-free search candidate"
            if entity_id == GLOBAL_ENTITY_ID
            else "no data - gap-fill candidate"
        )
        rows.append(row)
    return rows


def _read_or_create_main_rows(path: Path, schema: Schema) -> list[dict[str, str]]:
    if path.exists():
        return read_rows(path, required_columns=MAIN_INPUT_FIELDNAMES)
    return _main_input_skeleton_rows(schema)


def _mark_main_rows(
    main_rows: list[dict[str, str]],
    pinned_audit_rows: list[dict[str, str]],
    schema: Schema,
) -> list[dict[str, str]]:
    by_cell = {cell_key(row): row for row in pinned_audit_rows}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in main_rows:
        item = dict(row)
        key = cell_key(item)
        pinned = by_cell.get(key)
        if pinned:
            seen.add(key)
            item["pinned"] = "TRUE"
            for field in (
                "raw_value",
                "raw_units",
                "raw_basis_scale",
                "raw_basis_scale_units",
                "raw_basis_year",
                "source_key",
                "source_url",
                "page_ref",
                "quality_tag",
            ):
                item[field] = pinned.get(field, "")
            item["notes"] = pinned.get("notes", "pinned input")
        out.append(item)

    missing = sorted(set(by_cell) - seen)
    if missing:
        detail = ", ".join(f"({entity},{parameter})" for entity, parameter in missing)
        raise ValueError(f"Main Input skeleton is missing pinned cell(s): {detail}")

    skeleton = set(schema.skeleton_cells())
    extra = sorted(key for key in by_cell if key not in skeleton)
    if extra:
        detail = ", ".join(f"({entity},{parameter})" for entity, parameter in extra)
        raise ValueError(f"pinned cell(s) are outside schema skeleton: {detail}")
    return out


def _merge_audit_rows(existing_rows: list[dict[str, str]], pinned_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    pinned_cells = {cell_key(row) for row in pinned_rows}
    kept = [
        dict(row)
        for row in existing_rows
        if not (is_pinned_row(row) and cell_key(row) in pinned_cells)
    ]
    return kept + pinned_rows


def load_pinned_inputs(
    *,
    schema_path: str | Path,
    run_dir: str | Path = ".",
    pinned_path: str | Path | None = None,
    audit_path: str | Path | None = None,
    main_input_path: str | Path | None = None,
    sources_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Load pinned inputs and return a summary."""

    schema = load_schema(schema_path)
    run_dir = Path(run_dir)
    pinned_path = Path(pinned_path) if pinned_path is not None else run_dir / "pinned-inputs.csv"
    audit_path = Path(audit_path) if audit_path is not None else run_dir / "Audit.csv"
    main_input_path = (
        Path(main_input_path) if main_input_path is not None else run_dir / "Main Input.csv"
    )
    sources_path = Path(sources_path) if sources_path is not None else run_dir / "Sources.csv"

    rows = [
        row for row in read_rows(pinned_path, required_columns=REQUIRED_INPUT_COLUMNS)
        if _row_has_content(row)
    ]
    _validate_unique_cells(rows)
    _validate_pinned_rows(rows, schema, sources_path=sources_path)

    pinned_audit_rows = [
        pinned_to_audit_row(row, sources_path=sources_path)
        for row in rows
    ]
    existing_audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
    merged_audit_rows = _merge_audit_rows(existing_audit_rows, pinned_audit_rows)
    main_rows = _mark_main_rows(
        _read_or_create_main_rows(main_input_path, schema),
        pinned_audit_rows,
        schema,
    )

    if not dry_run:
        write_rows(audit_path, AUDIT_FIELDNAMES, merged_audit_rows)
        write_rows(main_input_path, MAIN_INPUT_FIELDNAMES, main_rows)

    return {
        "schema": schema,
        "pinned_path": pinned_path,
        "audit_path": audit_path,
        "main_input_path": main_input_path,
        "pinned_rows": len(pinned_audit_rows),
        "pinned_cells": sorted(cell_key(row) for row in pinned_audit_rows),
        "audit_rows": len(merged_audit_rows),
        "main_rows": len(main_rows),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--run-dir", type=Path, default=Path("."), help="Run directory")
    parser.add_argument("--pinned", type=Path, help="Pinned inputs CSV")
    parser.add_argument("--audit", type=Path, help="Audit.csv to update")
    parser.add_argument("--main-input", type=Path, help="Main Input.csv to mark")
    parser.add_argument("--sources", type=Path, help="Sources.csv for source_url fallback")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = load_pinned_inputs(
            schema_path=args.schema,
            run_dir=args.run_dir,
            pinned_path=args.pinned,
            audit_path=args.audit,
            main_input_path=args.main_input,
            sources_path=args.sources,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}loaded {result['pinned_rows']} pinned cell(s); "
        f"Audit rows={result['audit_rows']}, Main Input rows={result['main_rows']}"
    )
    for entity, parameter in result["pinned_cells"]:
        print(f"  pinned: {entity},{parameter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
