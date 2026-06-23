"""Collect current cross-source value disagreements into value_disagreements.csv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.consolidation import (
    DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
    fill_source_urls,
    find_value_disagreements,
    format_number,
    format_percent,
    read_audit_rows,
    validate_audit_cells,
)
from lib.csvio import CSV_SCHEMAS, column_names, read_rows, write_rows
from lib.schema import load_schema
from lib.source_url import SourceUrlError


VALUE_DISAGREEMENTS_FIELDNAMES = column_names(CSV_SCHEMAS["value_disagreements.csv"])
ANSWER_FIELDS = ("proposed_verdict", "analyst_answer", "notes")


def value_disagreement_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
        str(row.get("normalized_value") or "").strip(),
        str(row.get("cross_check_delta") or "").strip(),
        str(row.get("disagreement_group") or "").strip(),
    )


def _prior_answers(queue_path: str | Path) -> dict[tuple[str, str, str, str, str, str], dict[str, str]]:
    rows = read_rows(queue_path, required_columns=VALUE_DISAGREEMENTS_FIELDNAMES, missing_ok=True)
    answers: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if any((row.get(field) or "").strip() for field in ANSWER_FIELDS):
            answers[value_disagreement_key(row)] = {
                field: row.get(field, "") for field in ANSWER_FIELDS
            }
    return answers


def _question(item: Mapping[str, object], threshold: float) -> str:
    pct = format_percent(item.get("percent_from_average")) or "undefined because the group average is zero"
    return (
        f"Comparison value {format_number(float(item['comparison_value']))} "
        f"{item.get('comparison_units') or ''} from {item.get('source_key') or 'unknown source'} "
        f"for ({item.get('entity')},{item.get('parameter')}) is {pct} from group average "
        f"{format_number(float(item['group_average']))}. Should this row remain eligible for "
        f"consolidation, or be rejected as inconsistent? It differs by at least {threshold:.0%}."
    )


def value_disagreement_rows(
    *,
    schema_path: str | Path,
    audit_path: str | Path = "Audit_normalized.csv",
    sources_path: str | Path | None = "Sources.csv",
    prior_queue_path: str | Path | None = None,
    threshold: float = DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
) -> tuple[list[dict[str, str]], int]:
    schema = load_schema(schema_path)
    audit_rows = read_audit_rows(audit_path)
    fill_source_urls(audit_rows, sources_path)
    validate_audit_cells(audit_rows, schema)
    prior = _prior_answers(prior_queue_path) if prior_queue_path else {}

    rows: list[dict[str, str]] = []
    carried = 0
    for item in find_value_disagreements(audit_rows, schema, threshold):
        source_row = item["row"]
        group = (
            f"avg={format_number(float(item['group_average']))}; "
            f"count={item['group_count']}; "
            f"min={format_number(float(item['group_min']))}; "
            f"max={format_number(float(item['group_max']))}; "
            f"values={item['group_values']}"
        )
        queue_row = {name: "" for name in VALUE_DISAGREEMENTS_FIELDNAMES}
        queue_row.update(
            {
                "entity": str(item["entity"]),
                "parameter": str(item["parameter"]),
                "source_key": str(item["source_key"] or ""),
                "source_url": str(item["source_url"] or ""),
                "normalized_value": str(source_row.get("normalized_value") or ""),
                "normalized_units": str(source_row.get("normalized_units") or ""),
                "quality_tag": str(item["quality_tag"] or ""),
                "cross_check_delta": (
                    f"{format_percent(item.get('percent_from_average')) or 'undefined'} "
                    "from group average"
                ),
                "disagreement_group": group,
                "notes": (
                    f"page_ref={source_row.get('page_ref') or ''}; "
                    f"comparison_value={format_number(float(item['comparison_value']))} "
                    f"{item.get('comparison_units') or ''}; "
                    f"comparison_steps={item.get('comparison_steps') or ''}; "
                    + _question(item, threshold)
                ),
            }
        )
        answer = prior.get(value_disagreement_key(queue_row))
        if answer:
            queue_row.update(answer)
            carried += 1
        rows.append(queue_row)
    return rows, carried


def sweep_value_disagreements(
    *,
    schema_path: str | Path,
    audit_path: str | Path = "Audit_normalized.csv",
    output_path: str | Path = "value_disagreements.csv",
    sources_path: str | Path | None = "Sources.csv",
    threshold: float = DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
    dry_run: bool = False,
) -> dict[str, object]:
    rows, carried = value_disagreement_rows(
        schema_path=schema_path,
        audit_path=audit_path,
        sources_path=sources_path,
        prior_queue_path=output_path,
        threshold=threshold,
    )
    if not dry_run:
        write_rows(output_path, VALUE_DISAGREEMENTS_FIELDNAMES, rows)
    return {"rows": rows, "carried": carried, "output_path": Path(output_path), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--audit", type=Path, default=Path("Audit_normalized.csv"), help="Normalized Audit CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("value_disagreements.csv"),
        help="Queue CSV to write",
    )
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"), help="Sources.csv")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
        help="Fractional group-deviation threshold (default: 0.30)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args(argv)

    if args.threshold < 0:
        print("ERROR: --threshold must be non-negative", file=sys.stderr)
        return 2
    try:
        result = sweep_value_disagreements(
            schema_path=args.schema,
            audit_path=args.audit,
            output_path=args.output,
            sources_path=args.sources,
            threshold=args.threshold,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, SourceUrlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{len(result['rows'])} value disagreement row(s) -> {args.output} "
        f"({result['carried']} prior answer(s) preserved)"
    )
    if result["rows"]:
        print("Next: fill proposed_verdict with accept/reject and analyst_answer, then run apply_value_disagreements.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
