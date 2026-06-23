"""Apply answered held_questions.csv verdicts back to Audit.csv.

Verdicts:
- accept: hold -> clear; the captured value flows downstream.
- reject: hold -> reject; raw value, page_ref, units, basis, and quality are blanked.
- re-extract: hold remains and a reextract_todo.csv worklist is written.

Rows with no verdict are left unresolved, so the hard block remains armed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import AUDIT_FIELDNAMES, CSV_SCHEMAS, column_names, read_rows, write_rows
from lib.extraction import NULLED_ON_REJECT, audit_hold_key


HELD_QUESTIONS_FIELDNAMES = column_names(CSV_SCHEMAS["held_questions.csv"])
REEXTRACT_FIELDNAMES = HELD_QUESTIONS_FIELDNAMES

VERDICT_ALIASES = {
    "accept": "accept",
    "yes": "accept",
    "keep": "accept",
    "clear": "accept",
    "reject": "reject",
    "no": "reject",
    "drop": "reject",
    "blank": "reject",
    "re-extract": "re-extract",
    "reextract": "re-extract",
    "re_extract": "re-extract",
    "re extract": "re-extract",
}


def normalize_verdict(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw not in VERDICT_ALIASES:
        raise ValueError(f"unrecognized verdict {value!r}; use accept, reject, or re-extract")
    return VERDICT_ALIASES[raw]


def _queue_verdict(row: Mapping[str, object]) -> str | None:
    return normalize_verdict(str(row.get("proposed_verdict") or row.get("analyst_verdict") or ""))


def _append_note(row: dict[str, str], note: str) -> None:
    current = (row.get("extractor_notes") or "").strip()
    row["extractor_notes"] = f"{current} | {note}" if current else note


def _find_hold_index(rows: list[dict[str, str]], queue_row: Mapping[str, object]) -> int | None:
    key = audit_hold_key(queue_row)
    fallback: int | None = None
    for idx, row in enumerate(rows):
        if audit_hold_key(row) != key:
            continue
        if (row.get("relevance_status") or "").strip().lower() == "hold":
            return idx
        if fallback is None:
            fallback = idx
    return fallback


def apply_verdicts(
    *,
    audit_path: str | Path = "Audit.csv",
    queue_path: str | Path = "held_questions.csv",
    reextract_todo_path: str | Path = "reextract_todo.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES)
    queue_rows = read_rows(queue_path, required_columns=HELD_QUESTIONS_FIELDNAMES)

    counts = {"accept": 0, "reject": 0, "re-extract": 0, "unresolved": 0, "unmatched": 0}
    reextract_rows: list[dict[str, str]] = []
    errors: list[str] = []

    parsed: list[tuple[dict[str, str], str | None]] = []
    for idx, queue_row in enumerate(queue_rows):
        try:
            verdict = _queue_verdict(queue_row)
        except ValueError as exc:
            errors.append(f"row {idx}: {exc}")
            continue
        parsed.append((queue_row, verdict))
        if verdict is None:
            counts["unresolved"] += 1

    if errors:
        raise ValueError("\n".join(errors))

    for queue_row, verdict in parsed:
        if verdict is None:
            continue
        match_idx = _find_hold_index(audit_rows, queue_row)
        if match_idx is None:
            counts["unmatched"] += 1
            continue
        row = audit_rows[match_idx]
        answer = (queue_row.get("analyst_answer") or "").strip()

        if verdict == "accept":
            row["relevance_status"] = "clear"
            row["analyst_question"] = ""
            note = "RESOLVED extraction hold: accepted"
            if answer:
                note += f" - {answer}"
            _append_note(row, note)
            counts["accept"] += 1
        elif verdict == "reject":
            for key in NULLED_ON_REJECT:
                row[key] = ""
            row["relevance_status"] = "reject"
            row["analyst_question"] = ""
            note = "RESOLVED extraction hold: rejected"
            if answer:
                note += f" - {answer}"
            _append_note(row, note)
            counts["reject"] += 1
        else:
            row["relevance_status"] = "hold"
            note = "RE-EXTRACT requested"
            if answer:
                note += f" - {answer}"
            _append_note(row, note)
            reextract_rows.append({name: queue_row.get(name, "") for name in REEXTRACT_FIELDNAMES})
            counts["re-extract"] += 1

    if not dry_run:
        write_rows(audit_path, AUDIT_FIELDNAMES, audit_rows)
        if reextract_rows:
            write_rows(reextract_todo_path, REEXTRACT_FIELDNAMES, reextract_rows)

    return {
        "counts": counts,
        "reextract_rows": reextract_rows,
        "audit_path": Path(audit_path),
        "queue_path": Path(queue_path),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit.csv to update")
    parser.add_argument("--queue", type=Path, default=Path("held_questions.csv"), help="Answered queue CSV")
    parser.add_argument(
        "--reextract-todo",
        type=Path,
        default=Path("reextract_todo.csv"),
        help="Where to write re-extract worklist",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize only")
    args = parser.parse_args(argv)

    try:
        result = apply_verdicts(
            audit_path=args.audit,
            queue_path=args.queue,
            reextract_todo_path=args.reextract_todo,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result["counts"]
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}resolved {counts['accept']} accept, {counts['reject']} reject, "
        f"{counts['re-extract']} re-extract; {counts['unresolved']} unresolved, "
        f"{counts['unmatched']} unmatched"
    )
    if counts["unresolved"] or counts["re-extract"]:
        print("NOTE: normalization remains blocked while hold rows remain in Audit.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
