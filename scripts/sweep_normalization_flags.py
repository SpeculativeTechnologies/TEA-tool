"""Collect FLAGGED normalization rows into normalization_flags.csv."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import CSV_SCHEMAS, column_names, read_rows, write_rows


NORMALIZATION_FLAGS_FIELDNAMES = column_names(CSV_SCHEMAS["normalization_flags.csv"])
ANSWER_FIELDS = ("proposed_action", "analyst_answer", "notes")
RESOLVED_STATUSES = {"clear", "reject", "rejected", "drop", "dropped"}


def normalization_flag_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
        str(row.get("raw_value") or "").strip(),
        str(row.get("raw_units") or "").strip(),
    )


def _prior_answers(queue_path: str | Path) -> dict[tuple[str, str, str, str, str], dict[str, str]]:
    rows = read_rows(queue_path, required_columns=NORMALIZATION_FLAGS_FIELDNAMES, missing_ok=True)
    answers: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if any((row.get(field) or "").strip() for field in ANSWER_FIELDS):
            answers[normalization_flag_key(row)] = {field: row.get(field, "") for field in ANSWER_FIELDS}
    return answers


def _flag_reason(transform_steps: str) -> str:
    matches = re.findall(r"FLAGGED:\s*([^|]+)", transform_steps or "")
    return " | ".join(reason.strip() for reason in matches) or transform_steps


def normalization_flag_rows(
    audit_path: str | Path,
    *,
    prior_queue_path: str | Path | None = None,
) -> tuple[list[dict[str, str]], int]:
    audit_rows = read_rows(
        audit_path,
        required_columns=[
            "entity",
            "parameter",
            "source_key",
            "source_url",
            "raw_value",
            "raw_units",
            "transform_steps",
        ],
        missing_ok=True,
    )
    prior = _prior_answers(prior_queue_path) if prior_queue_path else {}
    carried = 0
    out: list[dict[str, str]] = []
    for row in audit_rows:
        status = (row.get("normalization_status") or "").strip().lower()
        if status in RESOLVED_STATUSES:
            continue
        if "FLAGGED:" not in (row.get("transform_steps") or ""):
            continue
        queue_row = {name: row.get(name, "") for name in NORMALIZATION_FLAGS_FIELDNAMES}
        queue_row["flag_reason"] = _flag_reason(row.get("transform_steps") or "")
        queue_row["proposed_action"] = ""
        queue_row["analyst_answer"] = ""
        note = (
            f"page_ref={row.get('page_ref') or ''}; transform_steps="
            f"{row.get('transform_steps') or ''}"
        )
        queue_row["notes"] = note
        answer = prior.get(normalization_flag_key(row))
        if answer:
            queue_row.update(answer)
            carried += 1
        out.append(queue_row)
    return out, carried


def sweep_normalization_flags(
    *,
    audit_path: str | Path = "Audit_normalized.csv",
    output_path: str | Path = "normalization_flags.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    rows, carried = normalization_flag_rows(audit_path, prior_queue_path=output_path)
    if not dry_run:
        write_rows(output_path, NORMALIZATION_FLAGS_FIELDNAMES, rows)
    return {"rows": rows, "carried": carried, "output_path": Path(output_path), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, default=Path("Audit_normalized.csv"), help="Normalized Audit CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("normalization_flags.csv"),
        help="Queue CSV to write",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args(argv)

    try:
        result = sweep_normalization_flags(
            audit_path=args.audit,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{len(result['rows'])} normalization flag row(s) -> {args.output} "
        f"({result['carried']} prior answer(s) preserved)"
    )
    if result["rows"]:
        print("Next: fill proposed_action with agent calc or reject, then run apply_normalization_flags.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
