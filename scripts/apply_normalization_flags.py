"""Apply answered normalization_flags.csv routing decisions to Audit.csv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import AUDIT_FIELDNAMES, read_rows, write_rows
from sweep_normalization_flags import NORMALIZATION_FLAGS_FIELDNAMES, normalization_flag_key


VERDICT_ALIASES = {
    "agent calc": "agent_calc",
    "agent_calc": "agent_calc",
    "agent-calc": "agent_calc",
    "calc": "agent_calc",
    "calculate": "agent_calc",
    "agent": "agent_calc",
    "reject": "reject",
    "rejected": "reject",
    "no": "reject",
    "drop": "reject",
    "blank": "reject",
}

CAPEX_OUTPUTS = (
    "capex_usd",
    "capex_form",
    "capex_basis_year",
    "capex_basis_scale",
    "capex_basis_scale_units",
    "capex_notes",
    "review_value",
    "review_units",
    "review_steps",
)


def normalize_verdict(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw not in VERDICT_ALIASES:
        raise ValueError(f"unrecognized proposed_action {value!r}; use agent calc or reject")
    return VERDICT_ALIASES[raw]


def _append_step(row: dict[str, str], note: str) -> None:
    existing = (row.get("transform_steps") or "").strip()
    row["transform_steps"] = f"{existing} | {note}" if existing else note


def _match_row(rows: list[dict[str, str]], queue_row: Mapping[str, object]) -> int | None:
    q_key = normalization_flag_key(queue_row)
    fallback: int | None = None
    for idx, row in enumerate(rows):
        if normalization_flag_key(row) != q_key:
            continue
        if "FLAGGED:" in (row.get("transform_steps") or ""):
            return idx
        if fallback is None:
            fallback = idx
    return fallback


def _apply_agent_calc(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = (queue_row.get("analyst_answer") or "").strip()
    row["normalization_status"] = "agent_calc"
    row["normalization_decision"] = answer
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "PENDING normalization-agent calculation"
    if answer:
        note += f": {answer}"
    _append_step(row, note)


def _apply_reject(row: dict[str, str], queue_row: Mapping[str, object]) -> None:
    answer = (queue_row.get("analyst_answer") or "").strip()
    row["normalization_status"] = "reject"
    row["normalization_decision"] = answer
    row["normalized_value"] = ""
    row["normalized_units"] = ""
    for key in CAPEX_OUTPUTS:
        row[key] = ""
    row["selected_for_model"] = ""
    row["cross_check_delta"] = ""
    note = "REJECTED by normalization review"
    if answer:
        note += f": {answer}"
    _append_step(row, note)


def apply_normalization_flags(
    *,
    audit_path: str | Path = "Audit_normalized.csv",
    queue_path: str | Path = "normalization_flags.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES)
    queue_rows = read_rows(queue_path, required_columns=NORMALIZATION_FLAGS_FIELDNAMES)

    counts = {"agent_calc": 0, "reject": 0, "unresolved": 0, "unmatched": 0}
    parsed: list[tuple[dict[str, str], str | None]] = []
    errors: list[str] = []
    for idx, row in enumerate(queue_rows):
        try:
            verdict = normalize_verdict(row.get("proposed_action") or "")
        except ValueError as exc:
            errors.append(f"row {idx}: {exc}")
            continue
        if verdict is None:
            counts["unresolved"] += 1
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
        if verdict == "agent_calc":
            _apply_agent_calc(row, queue_row)
            counts["agent_calc"] += 1
        else:
            _apply_reject(row, queue_row)
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
    parser.add_argument("--queue", type=Path, default=Path("normalization_flags.csv"), help="Answered queue CSV")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize only")
    args = parser.parse_args(argv)

    try:
        result = apply_normalization_flags(
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
        f"{prefix}routed {counts['agent_calc']} agent calc, {counts['reject']} reject; "
        f"{counts['unresolved']} unresolved, {counts['unmatched']} unmatched"
    )
    if counts["agent_calc"] or counts["unresolved"]:
        print("NOTE: agent_calc/unresolved rows still need Phase 4.2 resolution before consolidation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
