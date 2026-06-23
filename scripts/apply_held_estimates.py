"""Apply held_estimates.csv verdicts back to Audit.csv.

Verdicts:
- accept: keep the E row and mark ``held_estimate_status=clear``.
- reject: mark the estimate rejected and blank model-value outputs.
- analyst-override: replace the value with the analyst's value, re-tag E -> D,
  and mark clear.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.consolidation import CAPEX_OUTPUTS
from lib.csvio import AUDIT_FIELDNAMES, CSV_SCHEMAS, column_names, read_rows, write_rows


HELD_ESTIMATES_FIELDNAMES = column_names(CSV_SCHEMAS["held_estimates.csv"])

VERDICT_ALIASES = {
    "accept": "accept",
    "accepted": "accept",
    "yes": "accept",
    "keep": "accept",
    "clear": "accept",
    "reject": "reject",
    "rejected": "reject",
    "no": "reject",
    "drop": "reject",
    "blank": "reject",
    "analyst-override": "analyst-override",
    "analyst_override": "analyst-override",
    "override": "analyst-override",
    "d": "analyst-override",
}


def normalize_verdict(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw not in VERDICT_ALIASES:
        raise ValueError(
            f"unrecognized proposed_verdict {value!r}; use accept, reject, or analyst-override"
        )
    return VERDICT_ALIASES[raw]


def _queue_verdict(row: Mapping[str, object]) -> str | None:
    return normalize_verdict(str(row.get("proposed_verdict") or row.get("analyst_verdict") or ""))


def _identity(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
    )


def _queue_value(row: Mapping[str, object]) -> str:
    return str(row.get("normalized_value") or row.get("capex_usd") or row.get("raw_value") or "").strip()


def _match_row(rows: list[dict[str, str]], queue_row: Mapping[str, object]) -> int | None:
    q_key = _identity(queue_row)
    q_value = _queue_value(queue_row)
    fallback: int | None = None
    for idx, row in enumerate(rows):
        if _identity(row) != q_key:
            continue
        if fallback is None:
            fallback = idx
        if q_value and _queue_value(row) != q_value:
            continue
        return idx
    return fallback


def _append_step(row: dict[str, str], note: str) -> None:
    existing = (row.get("transform_steps") or "").strip()
    row["transform_steps"] = f"{existing} | {note}" if existing else note


def _apply_accept(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = str(queue_row.get("analyst_answer") or "").strip()
    row["held_estimate_status"] = "clear"
    row["held_estimate_answer"] = answer
    row["relevance_status"] = "clear"
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "RESOLVED held estimate: accepted"
    if answer:
        note += f" - {answer}"
    _append_step(row, note)


def _blank_model_outputs(row: dict[str, str]) -> None:
    row["raw_value"] = ""
    row["raw_units"] = ""
    row["normalized_value"] = ""
    row["normalized_units"] = ""
    for key in CAPEX_OUTPUTS:
        row[key] = ""


def _apply_reject(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = str(queue_row.get("analyst_answer") or "").strip()
    _blank_model_outputs(row)
    row["held_estimate_status"] = "reject"
    row["held_estimate_answer"] = answer
    row["relevance_status"] = "reject"
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "REJECTED held estimate"
    if answer:
        note += f" - {answer}"
    _append_step(row, note)


def _apply_override(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    value = str(queue_row.get("analyst_value") or "").strip()
    units = str(queue_row.get("analyst_units") or "").strip()
    answer = str(queue_row.get("analyst_answer") or "").strip()
    row["quality_tag"] = "D"
    row["raw_value"] = value
    row["raw_units"] = units
    row["normalized_value"] = value
    row["normalized_units"] = units
    row["held_estimate_status"] = "clear"
    row["held_estimate_answer"] = answer
    row["relevance_status"] = "clear"
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = f"ANALYST OVERRIDE estimate: {value} {units}"
    if answer:
        note += f" - {answer}"
    _append_step(row, note)


def apply_held_estimates(
    *,
    audit_path: str | Path = "Audit.csv",
    queue_path: str | Path = "held_estimates.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES)
    queue_rows = read_rows(queue_path, required_columns=HELD_ESTIMATES_FIELDNAMES)

    counts = {"accept": 0, "reject": 0, "analyst-override": 0, "unresolved": 0, "unmatched": 0}
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
        elif not str(row.get("analyst_answer") or "").strip():
            errors.append(f"row {idx}: analyst_answer is required when proposed_verdict is filled")
        elif verdict == "analyst-override":
            if not str(row.get("analyst_value") or "").strip():
                errors.append(f"row {idx}: analyst_value is required for analyst-override")
            if not str(row.get("analyst_units") or "").strip():
                errors.append(f"row {idx}: analyst_units is required for analyst-override")
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
        row = audit_rows[match_idx]
        if verdict == "accept":
            _apply_accept(row, queue_row)
            counts["accept"] += 1
        elif verdict == "reject":
            _apply_reject(row, queue_row)
            counts["reject"] += 1
        else:
            _apply_override(row, queue_row)
            counts["analyst-override"] += 1

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
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit CSV to update")
    parser.add_argument("--queue", type=Path, default=Path("held_estimates.csv"), help="Answered queue CSV")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize only")
    args = parser.parse_args(argv)

    try:
        result = apply_held_estimates(
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
        f"{prefix}resolved {counts['accept']} accept, {counts['reject']} reject, "
        f"{counts['analyst-override']} override; {counts['unresolved']} unresolved, "
        f"{counts['unmatched']} unmatched"
    )
    if counts["unresolved"]:
        print("NOTE: E rows without verdicts remain held for consolidation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
