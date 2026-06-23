"""Register approved search candidates in Sources.csv.

Rows are appended only after the analyst has approved/downloaded a source and
``rename_sources.py`` (or manual review) has left a file whose stem is either
``source_key`` or ends with ``_{source_key}``. Candidate JSON entries without a
matched file remain search history and are not registered.

Examples:
    python scripts/register_sources.py --schema tea-schema.json --input master-list.json --source-dir "master list sources" --sources Sources.csv
    python scripts/register_sources.py --schema tea-schema.json --input gap-fill-1A.json --source-dir "gap fill sources" --sources Sources.csv --mode gap --entity 1A
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from lib.csvio import SOURCES_FIELDNAMES, append_rows, read_rows
from lib.schema import load_schema
from lib.search import (
    SearchValidationError,
    candidate_to_source_row,
    source_file_present_for,
    validate_search_file,
)


def existing_source_keys(sources_path: str | Path) -> set[str]:
    """Return source keys already present in Sources.csv."""

    rows = read_rows(
        sources_path,
        required_columns=["source_key", "source_url", "source_role"],
        missing_ok=True,
    )
    return {
        (row.get("source_key") or "").strip()
        for row in rows
        if (row.get("source_key") or "").strip()
    }


def register_sources(
    *,
    schema_path: str | Path,
    input_path: str | Path,
    source_dir: str | Path,
    sources_path: str | Path,
    mode: str = "master",
    entity_id: str | None = None,
    uncovered_parameters: list[str] | None = None,
    approved_source_keys: list[str] | None = None,
    access_date: str | None = None,
    source_role: str = "extraction",
    dry_run: bool = False,
) -> dict[str, object]:
    """Append newly approved candidate rows to Sources.csv."""

    if source_role not in {"extraction", "estimate", "both"}:
        raise ValueError("source_role must be extraction, estimate, or both")

    schema = load_schema(schema_path)
    candidates = validate_search_file(
        input_path,
        schema,
        mode=mode,
        entity_id=entity_id,
        uncovered_parameters=uncovered_parameters or [],
        approved_source_keys=approved_source_keys or [],
    )
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    access_date = access_date or dt.date.today().isoformat()
    existing = existing_source_keys(sources_path)

    rows_to_append: list[dict[str, str]] = []
    skipped_no_file: list[str] = []
    skipped_duplicate: list[str] = []
    seen_input: set[str] = set()

    for candidate in candidates:
        if candidate.source_key in seen_input:
            continue
        seen_input.add(candidate.source_key)
        if candidate.source_key in existing:
            skipped_duplicate.append(candidate.source_key)
            continue
        if source_file_present_for(candidate.source_key, source_dir) is None:
            skipped_no_file.append(candidate.source_key)
            continue
        rows_to_append.append(
            candidate_to_source_row(
                candidate,
                access_date=access_date,
                source_role=source_role,
            )
        )

    if not dry_run and rows_to_append:
        append_rows(sources_path, SOURCES_FIELDNAMES, rows_to_append)

    return {
        "candidates": candidates,
        "rows": rows_to_append,
        "skipped_no_file": skipped_no_file,
        "skipped_duplicate": skipped_duplicate,
        "sources_path": Path(sources_path),
        "dry_run": dry_run,
    }


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--input", type=Path, required=True, help="Master-list or gap-fill JSON")
    parser.add_argument("--source-dir", type=Path, required=True, help="Folder with approved source files")
    parser.add_argument("--sources", type=Path, required=True, help="Sources.csv to append to")
    parser.add_argument("--mode", choices=("master", "gap"), default="master")
    parser.add_argument("--entity", dest="entity_id", help="Target entity id for gap mode")
    parser.add_argument(
        "--uncovered-parameters",
        help="Comma-separated parameter ids this gap-fill run is allowed to cover",
    )
    parser.add_argument(
        "--approved-source-keys",
        help="Comma-separated master-list source keys already approved (gap mode duplicate guard)",
    )
    parser.add_argument(
        "--source-role",
        choices=("extraction", "estimate", "both"),
        default="extraction",
        help="Role written to Sources.csv",
    )
    parser.add_argument("--access-date", help="Access date for new rows (YYYY-MM-DD; default today)")
    parser.add_argument("--dry-run", action="store_true", help="Report planned appends only")
    args = parser.parse_args(argv)

    try:
        result = register_sources(
            schema_path=args.schema,
            input_path=args.input,
            source_dir=args.source_dir,
            sources_path=args.sources,
            mode=args.mode,
            entity_id=args.entity_id,
            uncovered_parameters=_split_csv(args.uncovered_parameters),
            approved_source_keys=_split_csv(args.approved_source_keys),
            access_date=args.access_date,
            source_role=args.source_role,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, SearchValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    for row in result["rows"]:
        print(f"{prefix}append: {row['source_key']} ({row['source_url']})")

    print(
        f"{prefix}{len(result['rows'])} row(s) "
        f"{'would be appended' if args.dry_run else 'appended'} to {args.sources}. "
        f"Skipped {len(result['skipped_no_file'])} (no source file) and "
        f"{len(result['skipped_duplicate'])} (already present)."
    )
    if result["skipped_no_file"]:
        print("no-source-file source_keys: " + ", ".join(result["skipped_no_file"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
