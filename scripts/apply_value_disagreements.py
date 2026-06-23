"""Apply answered value_disagreements.csv verdicts to Audit.csv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.consolidation import CAPEX_OUTPUTS
from lib.csvio import AUDIT_FIELDNAMES, read_rows, write_rows
from sweep_value_disagreements import VALUE_DISAGREEMENTS_FIELDNAMES


VERDICT_ALIASES = {
    "accept": "accept",
    "yes": "accept",
    "keep": "accept",
    "clear": "accept",
    "reject": "reject",
    "rejected": "reject",
    "no": "reject",
    "drop": "reject",
    "blank": "reject",
}


def normalize_verdict(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw not in VERDICT_ALIASES:
        raise ValueError(f"unrecognized proposed_verdict {value!r}; use accept or reject")
    return VERDICT_ALIASES[raw]


def _queue_verdict(row: Mapping[str, object]) -> str | None:
    return normalize_verdict(str(row.get("proposed_verdict") or row.get("analyst_verdict") or ""))


def _identity(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
    )


def _match_row(rows: list[dict[str, str]], queue_row: Mapping[str, object]) -> int | None:
    q_key = _identity(queue_row)
    q_value = str(queue_row.get("normalized_value") or "").strip()
    fallback: int | None = None
    for idx, row in enumerate(rows):
        if _identity(row) != q_key:
            continue
        if fallback is None:
            fallback = idx
        if q_value and str(row.get("normalized_value") or "").strip() != q_value:
            continue
        return idx
    return fallback


def _append_step(row: dict[str, str], note: str) -> None:
    existing = (row.get("transform_steps") or "").strip()
    row["transform_steps"] = f"{existing} | {note}" if existing else note


def _apply_accept(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = str(queue_row.get("analyst_answer") or "").strip()
    row["disagreement_status"] = "clear"
    row["disagreement_decision"] = answer
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "RESOLVED value disagreement: accepted"
    if answer:
        note += f" - {answer}"
    _append_step(row, note)


def _apply_reject(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = str(queue_row.get("analyst_answer") or "").strip()
    original_value = row.get("review_value") or row.get("normalized_value") or ""
    original_units = row.get("review_units") or row.get("normalized_units") or ""
    row["disagreement_status"] = "reject"
    row["disagreement_decision"] = answer
    row["normalized_value"] = ""
    row["normalized_units"] = ""
    for key in CAPEX_OUTPUTS:
        row[key] = ""
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "REJECTED value disagreement"
    if original_value:
        note += f": comparison value {original_value} {original_units} excluded"
    if answer:
        note += f" - {answer}"
    _append_step(row, note)


def apply_value_disagreements(
    *,
    audit_path: str | Path = "Audit_normalized.csv",
    queue_path: str | Path = "value_disagreements.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES)
    queue_rows = read_rows(queue_path, required_columns=VALUE_DISAGREEMENTS_FIELDNAMES)

    counts = {"accept": 0, "reject": 0, "unresolved": 0, "unmatched": 0}
    parsed: list[tuple[dict[str, str], str | None]] = []
    errors: list[str] = []
    for idx, row in enumerate(queue_rows, start=2):
        try:
            verdict = _queue_verdict(row)
        except ValueError as exc:
            errors.append(f"row {idx}: {exc}")
            continue
        if verdict is None:
            counts["unresolved"] += 1
        elif not (row.get("analyst_answer") or "").strip():
            errors.append(f"row {idx}: analyst_answer is required when proposed_verdict is filled")
        parsed.append((row, verdict))
    if errors:
        raise ValueError("\n".join(errors))

    for queue_row, verdict in parsed:
        if verdict is None:
            continue
        match_idx = _match_row(audit_rows, queue_row)
        if match_idx is None:
            counts["unmatched"] += 1
            continue
        if verdict == "accept":
            _apply_accept(audit_rows[match_idx], queue_row)
            counts["accept"] += 1
        else:
            _apply_reject(audit_rows[match_idx], queue_row)
            counts["reject"] += 1

    if not dry_run:
        write_rows(audit_path, AUDIT_FIELDNAMES, audit_rows)
    return {
        "counts": counts,
        "audit_path": Path(audit_path),
        "queue_path": Path(queue_path),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, default=Path("Audit_normalized.csv"), help="Audit CSV to update")
    parser.add_argument("--queue", type=Path, default=Path("value_disagreements.csv"), help="Answered queue CSV")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize only")
    args = parser.parse_args(argv)

    try:
        result = apply_value_disagreements(
            audit_path=args.audit,
            queue_path=args.queue,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result["counts"]
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}resolved {counts['accept']} accept, {counts['reject']} reject; "
        f"{counts['unresolved']} unresolved, {counts['unmatched']} unmatched"
    )
    if counts["unresolved"]:
        print("NOTE: consolidation remains blocked while current disagreement rows are unresolved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
