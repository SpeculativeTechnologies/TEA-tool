"""Create empty working CSVs from a tea-schema.json config.

T2 replaces Vicky TEA's hardcoded unit/field workbook builder with a
config-driven skeleton:

    python scripts/build_csvs.py --schema runs/my-run/tea-schema.json
    python scripts/build_csvs.py --schema tests/fixtures/ti-6al-4v.tea-schema.json --output-dir tmp/run --force

The builder writes:
- Audit.csv: header only
- Sources.csv: header only, with source_url and source_role
- Main Input.csv: one skeleton row per Schema.skeleton_cells(), including REF
  rows for reference values

If pinned-inputs.csv is present, the builder calls the T8 loader to append
Audit rows with relevance_status=pinned and mark the matching Main Input cells.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from lib.csvio import (
    AUDIT_FIELDNAMES,
    MAIN_INPUT_FIELDNAMES,
    SOURCES_FIELDNAMES,
    blank_row,
    file_is_nonempty,
    write_rows,
)
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema


REPO_ROOT = Path(__file__).resolve().parent.parent

WORKING_CSVS = ("Audit.csv", "Sources.csv", "Main Input.csv")
SOURCE_DIRS = ("master list sources", "gap fill sources", "sources")


def main_input_skeleton_rows(schema: Schema) -> list[dict[str, str]]:
    """Build one blank Main Input row per schema skeleton cell."""

    rows: list[dict[str, str]] = []
    for entity_id, parameter_id in schema.skeleton_cells():
        row = blank_row(MAIN_INPUT_FIELDNAMES)
        row["entity"] = entity_id
        row["parameter"] = parameter_id
        if entity_id == GLOBAL_ENTITY_ID:
            row["notes"] = "no reference value - context-free search candidate"
        else:
            row["notes"] = "no data - gap-fill candidate"
        rows.append(row)
    return rows


def _write_audit(path: Path, schema: Schema) -> int:
    del schema
    return write_rows(path, AUDIT_FIELDNAMES, [])


def _write_sources(path: Path, schema: Schema) -> int:
    del schema
    return write_rows(path, SOURCES_FIELDNAMES, [])


def _write_main_input(path: Path, schema: Schema) -> int:
    return write_rows(path, MAIN_INPUT_FIELDNAMES, main_input_skeleton_rows(schema))


def _maybe_write(
    label: str,
    path: Path,
    writer: Callable[[Path, Schema], int],
    schema: Schema,
    *,
    force: bool,
    dry_run: bool,
    summary: str,
) -> tuple[str, Path, str]:
    if file_is_nonempty(path) and not force:
        return (label, path, "skip (exists, non-empty; use --force to overwrite)")
    if dry_run:
        return (label, path, f"would write: {summary}")
    count = writer(path, schema)
    suffix = f" ({count} data rows)" if count else ""
    return (label, path, f"wrote {summary}{suffix}")


def _ensure_source_dirs(output_dir: Path, *, dry_run: bool) -> list[tuple[str, Path, str]]:
    actions: list[tuple[str, Path, str]] = []
    for dirname in SOURCE_DIRS:
        path = output_dir / dirname
        label = dirname + "/"
        if path.is_dir():
            actions.append((label, path, "skip (already exists)"))
            continue
        if dry_run:
            actions.append((label, path, "would create directory + .gitkeep"))
            continue
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch(exist_ok=True)
        actions.append((label, path, "created directory + .gitkeep"))
    return actions


def _maybe_load_pinned_inputs(
    schema_path: Path,
    output_dir: Path,
    *,
    dry_run: bool,
) -> tuple[str, Path, str] | None:
    pinned_path = output_dir / "pinned-inputs.csv"
    if not pinned_path.exists():
        return None
    if dry_run:
        return ("pinned-inputs.csv", pinned_path, "would delegate to scripts/load_pinned_inputs.py")

    from load_pinned_inputs import load_pinned_inputs  # type: ignore
    load_pinned_inputs(schema_path=schema_path, run_dir=output_dir)
    return ("pinned-inputs.csv", pinned_path, "loaded via scripts/load_pinned_inputs.py")


def build(
    schema_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Build working CSVs for a run and return an action summary."""

    schema_path = Path(schema_path)
    schema = load_schema(schema_path)
    output_dir = Path(output_dir) if output_dir is not None else schema_path.parent

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    skeleton_count = len(main_input_skeleton_rows(schema))
    actions: list[tuple[str, Path, str]] = [
        _maybe_write(
            "Audit.csv",
            output_dir / "Audit.csv",
            _write_audit,
            schema,
            force=force,
            dry_run=dry_run,
            summary=f"{len(AUDIT_FIELDNAMES)} cols, empty",
        ),
        _maybe_write(
            "Sources.csv",
            output_dir / "Sources.csv",
            _write_sources,
            schema,
            force=force,
            dry_run=dry_run,
            summary=f"{len(SOURCES_FIELDNAMES)} cols, empty",
        ),
        _maybe_write(
            "Main Input.csv",
            output_dir / "Main Input.csv",
            _write_main_input,
            schema,
            force=force,
            dry_run=dry_run,
            summary=f"{len(MAIN_INPUT_FIELDNAMES)} cols, {skeleton_count} skeleton rows",
        ),
    ]

    actions.extend(_ensure_source_dirs(output_dir, dry_run=dry_run))
    pinned_action = _maybe_load_pinned_inputs(schema_path, output_dir, dry_run=dry_run)
    if pinned_action:
        actions.append(pinned_action)

    return {
        "schema": schema,
        "output_dir": output_dir,
        "skeleton_rows": skeleton_count,
        "actions": actions,
    }


def _default_schema_path(output_dir: Path) -> Path:
    candidate = output_dir / "tea-schema.json"
    if candidate.exists():
        return candidate
    return REPO_ROOT / "tea-schema.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--schema",
        type=Path,
        help="Path to tea-schema.json. Defaults to <output-dir>/tea-schema.json if present.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Run directory for working CSVs (default: current directory).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-empty CSVs.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned actions, write nothing.")
    args = parser.parse_args(argv)

    schema_path = args.schema or _default_schema_path(args.output_dir)
    result = build(
        schema_path,
        output_dir=args.output_dir,
        force=args.force,
        dry_run=args.dry_run,
    )
    for label, path, message in result["actions"]:
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}{label} -> {path}: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
