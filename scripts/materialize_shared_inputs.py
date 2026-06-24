"""Materialize comparison shared inputs into option run folders.

This script copies shared sources into each option ``Sources.csv`` and writes
shared evidence rows into each option ``Audit.csv`` and ``Main Input.csv``.
Rows are idempotent: rerunning replaces prior ``input_origin=shared`` rows for
the same mapped target cells.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from build_csvs import main_input_skeleton_rows
from lib.csvio import (
    AUDIT_FIELDNAMES,
    MAIN_INPUT_FIELDNAMES,
    SOURCES_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from lib.shared_inputs import SHARED_ORIGIN, cell_key, is_shared_row
from validate_comparison_project import ComparisonProjectError, load_project


class SharedMaterializationError(ValueError):
    """Raised when shared inputs cannot be safely materialized."""


AUDIT_SHARED_FIELDS = (
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "source_key",
    "source_url",
    "page_ref",
    "quality_tag",
    "notes",
)


MAIN_SHARED_FIELDS = (
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "source_key",
    "source_url",
    "page_ref",
    "quality_tag",
    "input_origin",
    "notes",
)


def _index(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {str(row.get(key) or "").strip(): row for row in rows if str(row.get(key) or "").strip()}


def _merge_sources(
    existing: list[dict[str, str]],
    shared_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    by_key = {str(row.get("source_key") or "").strip(): dict(row) for row in existing}
    for shared in shared_rows:
        key = str(shared.get("source_key") or "").strip()
        if not key:
            continue
        prior = by_key.get(key)
        if prior:
            prior_url = str(prior.get("source_url") or "").strip()
            shared_url = str(shared.get("source_url") or "").strip()
            if prior_url and shared_url and prior_url != shared_url:
                raise SharedMaterializationError(
                    f"source_key {key!r} has conflicting source_url in option Sources.csv"
                )
            merged = dict(prior)
            for field in SOURCES_FIELDNAMES:
                if not merged.get(field) and shared.get(field):
                    merged[field] = shared[field]
            by_key[key] = merged
        else:
            by_key[key] = dict(shared)
    return [by_key[key] for key in sorted(by_key)]


def _shared_audit_row(
    *,
    mapping: Mapping[str, str],
    shared_input: Mapping[str, str],
    shared_source: Mapping[str, str],
) -> dict[str, str]:
    row = blank_row(AUDIT_FIELDNAMES)
    row["entity"] = str(mapping.get("entity") or "").strip()
    row["parameter"] = str(mapping.get("parameter") or "").strip()
    row["source_key"] = str(shared_input.get("source_key") or "").strip()
    row["source_url"] = str(shared_source.get("source_url") or "").strip()
    for field in ("raw_value", "raw_units", "raw_basis_scale", "raw_basis_scale_units",
                  "raw_basis_year", "page_ref", "quality_tag"):
        row[field] = str(shared_input.get(field) or "").strip()
    note_parts = [
        f"shared_input_id={str(shared_input.get('shared_input_id') or '').strip()}",
        str(shared_input.get("notes") or "").strip(),
        str(mapping.get("notes") or "").strip(),
    ]
    row["notes"] = " | ".join(part for part in note_parts if part)
    row["relevance_status"] = "clear"
    row["input_origin"] = SHARED_ORIGIN
    if not row["page_ref"]:
        row["page_ref"] = "shared-inputs.csv"
    return row


def _read_or_create_main_rows(path: Path, schema) -> list[dict[str, str]]:
    if path.exists():
        return read_rows(path, required_columns=MAIN_INPUT_FIELDNAMES)
    return main_input_skeleton_rows(schema)


def _merge_main_rows(
    existing: list[dict[str, str]],
    shared_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    shared_by_cell = {cell_key(row): row for row in shared_rows}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in existing:
        item = dict(row)
        shared = shared_by_cell.get(cell_key(item))
        if shared:
            seen.add(cell_key(item))
            for field in MAIN_SHARED_FIELDS:
                item[field] = str(shared.get(field) or "")
        out.append(item)
    missing = sorted(set(shared_by_cell) - seen)
    if missing:
        detail = ", ".join(f"({entity},{parameter})" for entity, parameter in missing)
        raise SharedMaterializationError(f"Main Input skeleton is missing shared target cell(s): {detail}")
    return out


def materialize_shared_inputs(
    *,
    project_dir: str | Path = ".",
    dry_run: bool = False,
) -> dict[str, object]:
    project = load_project(project_dir)
    shared_sources_by_key = _index(project.shared_sources, "source_key")
    shared_inputs_by_id = _index(project.shared_inputs, "shared_input_id")
    mappings_by_option: dict[str, list[dict[str, str]]] = {}
    for mapping in project.shared_mappings:
        option_id = str(mapping.get("option_id") or "").strip()
        mappings_by_option.setdefault(option_id, []).append(mapping)

    summaries: dict[str, dict[str, int]] = {}
    for option_id, option in project.options.items():
        mappings = mappings_by_option.get(option_id, [])
        if not mappings:
            summaries[option_id] = {"shared_rows": 0, "sources": 0}
            continue

        shared_audit_rows: list[dict[str, str]] = []
        source_rows: list[dict[str, str]] = []
        for mapping in mappings:
            shared_input = shared_inputs_by_id[str(mapping["shared_input_id"]).strip()]
            shared_source = shared_sources_by_key[str(shared_input["source_key"]).strip()]
            shared_audit_rows.append(
                _shared_audit_row(
                    mapping=mapping,
                    shared_input=shared_input,
                    shared_source=shared_source,
                )
            )
            source_rows.append(shared_source)

        option.run_dir.mkdir(parents=True, exist_ok=True)
        audit_path = option.run_dir / "Audit.csv"
        main_path = option.run_dir / "Main Input.csv"
        sources_path = option.run_dir / "Sources.csv"

        existing_audit = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
        shared_cells = {cell_key(row) for row in shared_audit_rows}
        merged_audit = [
            dict(row)
            for row in existing_audit
            if not (is_shared_row(row) and cell_key(row) in shared_cells)
        ] + shared_audit_rows

        existing_sources = read_rows(sources_path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)
        merged_sources = _merge_sources(existing_sources, source_rows)
        merged_main = _merge_main_rows(
            _read_or_create_main_rows(main_path, option.schema),
            shared_audit_rows,
        )

        if not dry_run:
            write_rows(sources_path, SOURCES_FIELDNAMES, merged_sources)
            write_rows(audit_path, AUDIT_FIELDNAMES, merged_audit)
            write_rows(main_path, MAIN_INPUT_FIELDNAMES, merged_main)

        summaries[option_id] = {
            "shared_rows": len(shared_audit_rows),
            "sources": len(source_rows),
        }

    return {
        "project": project,
        "options": summaries,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path("."), help="Comparison project folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = materialize_shared_inputs(project_dir=args.project_dir, dry_run=args.dry_run)
    except (OSError, ComparisonProjectError, SharedMaterializationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    for option_id, summary in result["options"].items():
        print(
            f"{prefix}{option_id}: materialized {summary['shared_rows']} shared row(s), "
            f"{summary['sources']} source reference(s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
