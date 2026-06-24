"""Consolidate normalized Audit rows into Main Input.csv.

For each schema-declared (entity, parameter) cell, the consolidator:

1. Blocks while current >=30% value disagreements lack analyst verdicts.
2. Blocks while same-quality top candidates need a scope-fit decision.
3. Ranks shared-input rows as authoritative, then quality tag,
   scope-fit decision, year, and source_key.
4. Sets selected_for_model/cross_check_delta in Audit and writes Main Input.

Examples:
    python scripts/consolidate.py --schema tea-schema.json --audit Audit_normalized.csv
    python scripts/consolidate.py --schema tea-schema.json --audit Audit_normalized.csv --in-place
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.consolidation import (
    DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
    FixedInputConflictError,
    HeldEstimateRowsError,
    ScopeFitDecisionRowsError,
    ValueDisagreementRowsError,
    build_main_input_rows,
    fill_source_urls,
    find_fixed_conflicts,
    find_scope_fit_decision_problems,
    find_unresolved_held_estimates,
    find_value_disagreements,
    format_fixed_conflict_error,
    format_held_estimate_error,
    format_scope_fit_error,
    format_value_disagreement_error,
    main_row_has_value,
    read_audit_rows,
    select_rows,
    validate_audit_cells,
    write_audit_rows,
    write_main_input_rows,
)
from lib.csvio import CSV_SCHEMAS, column_names, read_rows
from lib.schema import load_schema
from lib.source_url import SourceUrlError


SCOPE_FIT_FIELDNAMES = column_names(CSV_SCHEMAS["stage5_scope_fit_decisions.csv"])


def load_scope_fit_decisions(path: str | Path | None) -> dict[tuple[str, str], str]:
    if path is None:
        return {}
    decisions: dict[tuple[str, str], str] = {}
    rows = read_rows(path, required_columns=SCOPE_FIT_FIELDNAMES, missing_ok=True)
    for idx, row in enumerate(rows, start=2):
        entity = (row.get("entity") or "").strip()
        parameter = (row.get("parameter") or "").strip()
        decision = (row.get("decision") or row.get("source_key") or "").strip()
        if not entity and not parameter and not decision:
            continue
        if not entity or not parameter or not decision:
            raise ScopeFitDecisionRowsError(
                f"{path} row {idx}: entity, parameter, and decision are required"
            )
        key = (entity, parameter)
        if key in decisions and decisions[key] != decision:
            raise ScopeFitDecisionRowsError(
                f"{path} has conflicting decisions for ({entity},{parameter})"
            )
        decisions[key] = decision
    return decisions


def _default_main_input_path(audit_path: Path) -> Path:
    return audit_path.with_name("Main Input.csv")


def _default_audit_sidecar_path(audit_path: Path) -> Path:
    return audit_path.with_name(audit_path.stem + "_consolidated.csv")


def consolidate(
    *,
    schema_path: str | Path,
    audit_path: str | Path = "Audit_normalized.csv",
    main_input_path: str | Path | None = None,
    audit_output_path: str | Path | None = None,
    sources_path: str | Path | None = "Sources.csv",
    scope_fit_decisions_path: str | Path | None = "stage5_scope_fit_decisions.csv",
    value_disagreement_threshold: float = DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
    enforce_held_estimates: bool = True,
    in_place: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    audit_path = Path(audit_path)
    main_input_path = (
        Path(main_input_path) if main_input_path is not None else _default_main_input_path(audit_path)
    )
    audit_output_path = (
        audit_path if in_place
        else Path(audit_output_path) if audit_output_path is not None
        else _default_audit_sidecar_path(audit_path)
    )

    rows = read_audit_rows(audit_path)
    fill_source_urls(rows, sources_path)
    validate_audit_cells(rows, schema)

    fixed_conflicts = find_fixed_conflicts(rows, schema)
    if fixed_conflicts:
        raise FixedInputConflictError(format_fixed_conflict_error(fixed_conflicts))

    disagreements = find_value_disagreements(rows, schema, value_disagreement_threshold)
    if disagreements:
        raise ValueDisagreementRowsError(
            format_value_disagreement_error(disagreements, value_disagreement_threshold)
        )

    if enforce_held_estimates:
        unresolved_estimates = find_unresolved_held_estimates(rows)
        if unresolved_estimates:
            raise HeldEstimateRowsError(format_held_estimate_error(unresolved_estimates))

    scope_fit_decisions = load_scope_fit_decisions(scope_fit_decisions_path)
    scope_fit_problems = find_scope_fit_decision_problems(rows, schema, scope_fit_decisions)
    if scope_fit_problems:
        raise ScopeFitDecisionRowsError(format_scope_fit_error(scope_fit_problems))

    consolidated_rows = select_rows(rows, schema, scope_fit_decisions)
    main_rows = build_main_input_rows(consolidated_rows, schema)

    selected = sum(
        1 for row in consolidated_rows
        if (row.get("selected_for_model") or "").strip().upper() == "TRUE"
    )
    filled = sum(1 for row in main_rows if main_row_has_value(row))
    summary = {
        "audit_rows": len(rows),
        "selected": selected,
        "main_skeleton_rows": len(main_rows),
        "main_filled": filled,
        "gaps": len(main_rows) - filled,
        "audit_output_path": audit_output_path,
        "main_input_path": main_input_path,
        "dry_run": dry_run,
    }

    if not dry_run:
        write_audit_rows(audit_output_path, consolidated_rows)
        write_main_input_rows(main_input_path, main_rows)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("Audit_normalized.csv"),
        help="Normalized Audit CSV",
    )
    parser.add_argument(
        "--main-input",
        type=Path,
        help="Main Input CSV to write (default: beside --audit)",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Consolidated Audit sidecar path (default: <audit>_consolidated.csv)",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("Sources.csv"),
        help="Sources.csv used to fill missing source_url values",
    )
    parser.add_argument(
        "--scope-fit-decisions",
        type=Path,
        default=Path("stage5_scope_fit_decisions.csv"),
        help="CSV produced from prompts/scope-fit-agent.md",
    )
    parser.add_argument(
        "--value-disagreement-threshold",
        type=float,
        default=DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
        help="Fractional group-deviation threshold (default: 0.30)",
    )
    parser.add_argument("--skip-held-estimate-gate", action="store_true")
    parser.add_argument("--in-place", action="store_true", help="Overwrite --audit")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")
    args = parser.parse_args(argv)

    try:
        result = consolidate(
            schema_path=args.schema,
            audit_path=args.audit,
            main_input_path=args.main_input,
            audit_output_path=args.audit_output,
            sources_path=args.sources,
            scope_fit_decisions_path=args.scope_fit_decisions,
            value_disagreement_threshold=args.value_disagreement_threshold,
            enforce_held_estimates=not args.skip_held_estimate_gate,
            in_place=args.in_place,
            dry_run=args.dry_run,
        )
    except FixedInputConflictError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 7
    except ValueDisagreementRowsError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 4
    except ScopeFitDecisionRowsError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 5
    except HeldEstimateRowsError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 6
    except (OSError, ValueError, SourceUrlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}Audit: {result['audit_rows']} row(s), {result['selected']} selected. "
        f"Main Input: {result['main_filled']}/{result['main_skeleton_rows']} filled, "
        f"{result['gaps']} gap(s)."
    )
    if not args.dry_run:
        print(f"Audit -> {result['audit_output_path']}")
        print(f"Main Input -> {result['main_input_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
