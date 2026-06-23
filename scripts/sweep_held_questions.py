"""Collect unresolved extraction holds into held_questions.csv.

The queue is reviewer-facing and self-contained: it includes the source URL,
captured value, page reference, extractor question, and notes. Fill
``proposed_verdict`` with ``accept``, ``reject``, or ``re-extract``, then run
``apply_held_verdicts.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import CSV_SCHEMAS, column_names, read_rows, write_rows
from lib.extraction import audit_hold_key


HELD_QUESTIONS_FIELDNAMES = column_names(CSV_SCHEMAS["held_questions.csv"])
ANSWER_FIELDS = ("proposed_verdict", "analyst_answer", "notes")


def _answer_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    return audit_hold_key(row)


def _prior_answers(queue_path: str | Path) -> dict[tuple[str, str, str, str, str], dict[str, str]]:
    rows = read_rows(queue_path, required_columns=HELD_QUESTIONS_FIELDNAMES, missing_ok=True)
    answers: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if any((row.get(field) or "").strip() for field in ANSWER_FIELDS):
            answers[_answer_key(row)] = {field: row.get(field, "") for field in ANSWER_FIELDS}
    return answers


def held_question_rows(audit_path: str | Path, *, prior_queue_path: str | Path | None = None) -> tuple[list[dict[str, str]], int]:
    audit_rows = read_rows(
        audit_path,
        required_columns=["entity", "parameter", "source_key", "source_url", "relevance_status"],
        missing_ok=True,
    )
    prior = _prior_answers(prior_queue_path) if prior_queue_path else {}
    carried = 0
    out: list[dict[str, str]] = []
    for row in audit_rows:
        if (row.get("relevance_status") or "").strip().lower() != "hold":
            continue
        queue_row = {name: row.get(name, "") for name in HELD_QUESTIONS_FIELDNAMES}
        queue_row["relevance_status"] = "hold"
        answer = prior.get(_answer_key(queue_row))
        if answer:
            queue_row.update(answer)
            carried += 1
        out.append(queue_row)
    return out, carried


def sweep_held_questions(
    *,
    audit_path: str | Path = "Audit.csv",
    output_path: str | Path = "held_questions.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    rows, carried = held_question_rows(audit_path, prior_queue_path=output_path)
    if not dry_run:
        write_rows(output_path, HELD_QUESTIONS_FIELDNAMES, rows)
    return {"rows": rows, "carried": carried, "output_path": Path(output_path), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit.csv to scan")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("held_questions.csv"),
        help="Queue CSV to write",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args(argv)

    try:
        result = sweep_held_questions(
            audit_path=args.audit,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{len(result['rows'])} hold row(s) -> {args.output} "
        f"({result['carried']} prior answer(s) preserved)"
    )
    if result["rows"]:
        print("Next: fill proposed_verdict and analyst_answer, then run apply_held_verdicts.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
