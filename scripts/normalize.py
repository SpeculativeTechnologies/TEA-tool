"""Normalize Audit.csv rows using tea-schema.json rule types.

Examples:
    python scripts/normalize.py --schema tea-schema.json --audit Audit.csv --output Audit_normalized.csv
    python scripts/normalize.py --schema tea-schema.json --audit Audit_post_estimation.csv --only-quality-tag E
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.csvio import AUDIT_FIELDNAMES, read_rows, write_rows
from lib.extraction import ExtractionHoldError, assert_no_unresolved_holds
from lib.schema import load_schema
from lib.source_url import SourceUrlError, source_url_for
from lib.transforms import load_conventions, normalize_audit_row


def _default_output_path(audit_path: Path) -> Path:
    return audit_path.with_name(audit_path.stem + "_normalized.csv")


def _fill_source_urls(rows: list[dict[str, str]], sources_path: str | Path | None) -> None:
    if sources_path is None:
        return
    for row in rows:
        if (row.get("source_key") or "").strip() and not (row.get("source_url") or "").strip():
            row["source_url"] = source_url_for(row.get("source_key"), sources_path, required=True)


def normalize_audit(
    *,
    schema_path: str | Path,
    audit_path: str | Path = "Audit.csv",
    output_path: str | Path | None = None,
    conventions_dir: str | Path = "conventions",
    sources_path: str | Path | None = "Sources.csv",
    only_quality_tag: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    audit_path = Path(audit_path)
    output_path = Path(output_path) if output_path is not None else _default_output_path(audit_path)

    assert_no_unresolved_holds(audit_path)
    rows = read_rows(audit_path, required_columns=["entity", "parameter", "raw_value", "quality_tag"])
    _fill_source_urls(rows, sources_path)

    conv = load_conventions(schema, conventions_dir)
    # Accept one tag or a comma-separated set (e.g. "E,U" to re-normalize both
    # backed and unbacked estimate rows after Phase 6).
    tags = {t.strip().upper() for t in (only_quality_tag or "").split(",") if t.strip()}
    out_rows: list[dict[str, str]] = []
    counts = {"total": len(rows), "targeted": 0, "normalized": 0, "capex": 0, "flagged": 0}

    for row in rows:
        if tags and (row.get("quality_tag") or "").strip().upper() not in tags:
            out_rows.append(dict(row))
            continue
        counts["targeted"] += 1
        normalized = normalize_audit_row(row, schema, conv)
        if normalized.get("normalized_value"):
            counts["normalized"] += 1
        if normalized.get("capex_usd"):
            counts["capex"] += 1
        if "FLAGGED:" in (normalized.get("transform_steps") or ""):
            counts["flagged"] += 1
        out_rows.append(normalized)

    if not dry_run:
        write_rows(output_path, AUDIT_FIELDNAMES, out_rows)

    return {
        "rows": out_rows,
        "counts": counts,
        "audit_path": audit_path,
        "output_path": output_path,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit.csv to normalize")
    parser.add_argument("--output", type=Path, help="Output CSV path")
    parser.add_argument(
        "--conventions-dir",
        type=Path,
        default=Path("conventions"),
        help="Directory containing convention CSVs",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("Sources.csv"),
        help="Sources.csv used to fill missing source_url values; pass an absent path only if all source_url cells are already filled",
    )
    parser.add_argument(
        "--only-quality-tag",
        help="Normalize only rows with this quality_tag and copy all other rows unchanged",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")
    args = parser.parse_args(argv)

    try:
        result = normalize_audit(
            schema_path=args.schema,
            audit_path=args.audit,
            output_path=args.output,
            conventions_dir=args.conventions_dir,
            sources_path=args.sources,
            only_quality_tag=args.only_quality_tag,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, ExtractionHoldError, SourceUrlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result["counts"]
    prefix = "[dry-run] " if args.dry_run else ""
    if args.only_quality_tag:
        print(
            f"{prefix}processed {counts['targeted']} quality_tag={args.only_quality_tag} row(s) "
            f"({counts['normalized']} normalized, {counts['capex']} CAPEX, {counts['flagged']} flagged); "
            f"copied {counts['total'] - counts['targeted']} other row(s) -> {result['output_path']}"
        )
    else:
        print(
            f"{prefix}processed {counts['total']} row(s) "
            f"({counts['normalized']} normalized, {counts['capex']} CAPEX, {counts['flagged']} flagged) "
            f"-> {result['output_path']}"
        )
    if counts["flagged"]:
        print("Next: run sweep_normalization_flags.py and resolve flagged rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
