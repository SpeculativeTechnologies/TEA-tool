"""Finalize a run after consolidation without running a model.

Phase 7.1 emits the final Main Input table, a Reference Values table, and a
run manifest summarizing coverage, quality distribution, source counts, shared
inputs, residual gaps, and declared validation targets.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Mapping

from lib.consolidation import main_row_has_value
from lib.csvio import AUDIT_FIELDNAMES, MAIN_INPUT_FIELDNAMES, SOURCES_FIELDNAMES, read_rows, write_rows
from lib.shared_inputs import cell_key, is_shared_row
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema


def _quote(value: object) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    return text


def _validation_targets(schema: Schema) -> list[Mapping[str, object]]:
    return list(schema.validation_targets)


def _source_counts(sources_rows: list[dict[str, str]]) -> Counter:
    counts: Counter = Counter()
    for row in sources_rows:
        role = (row.get("source_role") or "unknown").strip().lower() or "unknown"
        counts[role] += 1
    return counts


def _quality_distribution(main_rows: list[dict[str, str]]) -> Counter:
    counts: Counter = Counter()
    for row in main_rows:
        if not main_row_has_value(row):
            continue
        tag = (row.get("quality_tag") or "untagged").strip() or "untagged"
        counts[tag] += 1
    return counts


def _gap_rows(main_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in main_rows if not main_row_has_value(row)]


def _shared_rows(main_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in main_rows if is_shared_row(row)]


def _validate_main_input(main_rows: list[dict[str, str]], schema: Schema) -> None:
    expected = schema.skeleton_cells()
    actual = [cell_key(row) for row in main_rows if row.get("entity") or row.get("parameter")]
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    duplicates = sorted({cell for cell in actual if actual.count(cell) > 1})
    errors: list[str] = []
    if missing:
        errors.append("missing schema cell(s): " + ", ".join(f"({e},{p})" for e, p in missing))
    if extra:
        errors.append("extra non-schema cell(s): " + ", ".join(f"({e},{p})" for e, p in extra))
    if duplicates:
        errors.append("duplicate cell(s): " + ", ".join(f"({e},{p})" for e, p in duplicates))
    if errors:
        raise ValueError("\n".join(errors))


def _numeric_model_value(row: Mapping[str, object]) -> float | None:
    populated = [
        str(row.get(key) or "").strip()
        for key in ("normalized_value", "capex_usd")
        if str(row.get(key) or "").strip()
    ]
    if len(populated) != 1:
        return None
    try:
        value = float(populated[0])
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _validate_complete(main_rows: list[dict[str, str]], schema: Schema) -> None:
    """Both modes: every TEA cell must end with one finite numeric model value.

    Auto resolves every gap automatically; Guided stays blocked until an
    approved estimate or a supplied value fills each blank (orchestrator §10).
    """

    invalid = [
        (row.get("entity", ""), row.get("parameter", ""))
        for row in main_rows
        if _numeric_model_value(row) is None
    ]
    if invalid:
        cells = ", ".join(f"({entity},{parameter})" for entity, parameter in invalid)
        mode = "Auto" if schema.is_auto else "Guided"
        raise ValueError(
            "finalization requires exactly one finite numeric model value for every "
            f"TEA cell ({mode} mode); incomplete/non-numeric cell(s): {cells}. "
            "Resolve each gap with an approved estimate or a supplied value (or pass "
            "--allow-gaps for a draft manifest that is not a final hand-off)."
        )


def _auto_review_markdown(
    *,
    schema: Schema,
    main_rows: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    run_log: str,
) -> str:
    lines = [
        f"# Auto Review - {schema.display_name}",
        "",
        "## Outcome",
        "",
        f"- Numeric TEA cells completed: {len(main_rows)}/{len(main_rows)}",
        "- Execution mode: `auto`",
        "",
        "## Gate Decisions",
        "",
    ]
    decisions = []
    decision_fields = (
        ("relevance_status", "extractor_notes"),
        ("normalization_status", "normalization_decision"),
        ("disagreement_status", "disagreement_decision"),
        ("held_estimate_status", "held_estimate_answer"),
    )
    for row in audit_rows:
        for status_field, reason_field in decision_fields:
            reason = str(row.get(reason_field) or "").strip()
            if not reason or "AUTO:" not in reason.upper():
                continue
            decisions.append(
                (
                    row.get("entity", ""),
                    row.get("parameter", ""),
                    status_field,
                    row.get(status_field, ""),
                    reason,
                )
            )
    if decisions:
        lines.extend(
            [
                "| entity | parameter | gate | decision | reasoning |",
                "|---|---|---|---|---|",
            ]
        )
        for entity, parameter, gate, decision, reason in decisions:
            lines.append(
                f"| {_quote(entity)} | {_quote(parameter)} | {_quote(gate)} | "
                f"{_quote(decision)} | {_quote(reason)} |"
            )
    else:
        lines.append("No row-level `AUTO:` gate decisions were found in the supplied Audit file.")

    lines.extend(["", "## Assumptions And Estimates", ""])
    estimates = [row for row in main_rows if (row.get("quality_tag") or "").strip().upper() == "E"]
    if estimates:
        lines.extend(
            [
                "| entity | parameter | numeric value | units | confidence / assumptions |",
                "|---|---|---:|---|---|",
            ]
        )
        for row in estimates:
            value = row.get("capex_usd") or row.get("normalized_value") or ""
            units = row.get("normalized_units") or row.get("capex_form") or ""
            justification = str(row.get("estimate_justification") or "").strip()
            summary = justification
            try:
                parsed = json.loads(justification) if justification else {}
                confidence = parsed.get("estimator_confidence", "unspecified")
                caveats = parsed.get("caveats") or []
                summary = f"confidence={confidence}; caveats={caveats}"
            except (TypeError, json.JSONDecodeError):
                pass
            lines.append(
                f"| {_quote(row.get('entity'))} | {_quote(row.get('parameter'))} | "
                f"{_quote(value)} | {_quote(units)} | {_quote(summary)} |"
            )
    else:
        lines.append("No E-quality estimates were selected.")

    lines.extend(["", "## Assumptions, Flags, And Technical Errors", ""])
    if run_log.strip():
        lines.append(run_log.strip())
    else:
        lines.append(
            "No separate `auto-run-log.md` was supplied. Review the gate decisions and "
            "estimate caveats above; no technical errors were recorded by finalization."
        )
    lines.append("")
    return "\n".join(lines)


def _manifest_markdown(
    *,
    schema: Schema,
    main_rows: list[dict[str, str]],
    sources_rows: list[dict[str, str]],
    main_output_path: Path,
    reference_output_path: Path,
) -> str:
    filled = [row for row in main_rows if main_row_has_value(row)]
    gaps = _gap_rows(main_rows)
    shared = _shared_rows(main_rows)
    source_counts = _source_counts(sources_rows)
    quality_counts = _quality_distribution(main_rows)
    validation_targets = _validation_targets(schema)

    lines = [
        f"# Run Manifest - {schema.display_name}",
        "",
        "## Summary",
        "",
        f"- TEA ID: `{schema.tea_id}`",
        f"- Execution mode: `{schema.execution_mode}`",
        f"- Functional unit: `{schema.functional_unit_symbol or schema.functional_unit_name}`",
        f"- Basis: `{schema.currency}`, `{schema.base_year}`, `{schema.inflation_index}`",
        f"- Main Input: `{main_output_path}`",
        f"- Reference Values: `{reference_output_path}`",
        f"- Coverage: {len(filled)}/{len(main_rows)} filled; {len(gaps)} residual gap(s)",
        f"- Shared input cells: {len(shared)}",
        "",
        "## Source Counts",
        "",
    ]
    if source_counts:
        for role, count in sorted(source_counts.items()):
            lines.append(f"- {role}: {count}")
    else:
        lines.append("- none registered")

    lines.extend(["", "## Quality Distribution", ""])
    if quality_counts:
        for tag, count in sorted(quality_counts.items()):
            lines.append(f"- {tag}: {count}")
    else:
        lines.append("- no filled cells")

    lines.extend(["", "## Shared Inputs", ""])
    if shared:
        lines.extend(["| entity | parameter | source_key | source_url |", "|---|---|---|---|"])
        for row in shared:
            lines.append(
                f"| {_quote(row.get('entity'))} | {_quote(row.get('parameter'))} | "
                f"{_quote(row.get('source_key'))} | {_quote(row.get('source_url'))} |"
            )
    else:
        lines.append("None.")

    lines.extend(["", "## Residual Gaps", ""])
    if gaps:
        lines.extend(["| entity | parameter | notes |", "|---|---|---|"])
        for row in gaps:
            lines.append(
                f"| {_quote(row.get('entity'))} | {_quote(row.get('parameter'))} | "
                f"{_quote(row.get('notes'))} |"
            )
    else:
        lines.append("None.")

    lines.extend(["", "## Validation Targets", ""])
    if validation_targets:
        for target in validation_targets:
            metric = target.get("metric", "target")
            lines.append(f"- {_quote(metric)}: `{_quote(target)}`")
    else:
        lines.append("None declared.")

    lines.extend(
        [
            "",
            "## Inputs Finalized",
            "",
            "Inputs are finalized: one finite numeric value per schema cell. A model can "
            "now be run on `Main Input.csv` — the `/tea-model` and `/tea-data` skills build "
            "and run one, or run your own.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_inputs(
    *,
    schema_path: str | Path,
    main_input_path: str | Path = "Main Input.csv",
    sources_path: str | Path = "Sources.csv",
    audit_path: str | Path | None = None,
    auto_run_log_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    require_complete: bool = True,
    dry_run: bool = False,
) -> dict[str, object]:
    """Finalize Main Input and write reference values plus run manifest.

    ``require_complete`` (default True) enforces the both-mode no-gap numeric
    contract. Pass False only for an explicitly-draft intermediate manifest that
    is not the final hand-off.
    """

    schema = load_schema(schema_path)
    main_input_path = Path(main_input_path)
    sources_path = Path(sources_path)
    output_dir = Path(output_dir) if output_dir is not None else main_input_path.parent
    manifest_path = (
        Path(manifest_path) if manifest_path is not None else output_dir / "run-manifest.md"
    )
    main_output_path = output_dir / "Main Input.csv"
    reference_output_path = output_dir / "Reference Values.csv"
    auto_review_path = output_dir / "auto-review.md"

    main_rows = read_rows(main_input_path, required_columns=MAIN_INPUT_FIELDNAMES)
    _validate_main_input(main_rows, schema)
    if require_complete:
        _validate_complete(main_rows, schema)
    sources_rows = read_rows(sources_path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)
    audit_rows = (
        read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
        if audit_path is not None
        else []
    )
    if auto_run_log_path is None:
        auto_run_log_path = main_input_path.parent / "auto-run-log.md"
    auto_run_log_path = Path(auto_run_log_path)
    run_log = auto_run_log_path.read_text(encoding="utf-8") if auto_run_log_path.exists() else ""
    reference_rows = [row for row in main_rows if row.get("entity") == GLOBAL_ENTITY_ID]
    manifest = _manifest_markdown(
        schema=schema,
        main_rows=main_rows,
        sources_rows=sources_rows,
        main_output_path=main_output_path,
        reference_output_path=reference_output_path,
    )
    auto_review = (
        _auto_review_markdown(
            schema=schema,
            main_rows=main_rows,
            audit_rows=audit_rows,
            run_log=run_log,
        )
        if schema.is_auto
        else ""
    )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        if main_input_path.resolve() != main_output_path.resolve():
            shutil.copyfile(main_input_path, main_output_path)
        write_rows(reference_output_path, MAIN_INPUT_FIELDNAMES, reference_rows)
        manifest_path.write_text(manifest, encoding="utf-8")
        if schema.is_auto:
            auto_review_path.write_text(auto_review, encoding="utf-8")

    gaps = _gap_rows(main_rows)
    shared = _shared_rows(main_rows)
    return {
        "schema": schema,
        "main_input_path": main_input_path,
        "main_output_path": main_output_path,
        "reference_output_path": reference_output_path,
        "manifest_path": manifest_path,
        "auto_review_path": auto_review_path if schema.is_auto else None,
        "main_rows": len(main_rows),
        "filled": len(main_rows) - len(gaps),
        "gaps": len(gaps),
        "shared": len(shared),
        "reference_rows": len(reference_rows),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--main-input", type=Path, default=Path("Main Input.csv"))
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"))
    parser.add_argument("--audit", type=Path, help="Final consolidated Audit CSV for Auto reasoning")
    parser.add_argument("--auto-run-log", type=Path, help="Optional Auto assumptions/errors log")
    parser.add_argument("--output-dir", type=Path, help="Directory for final artifacts")
    parser.add_argument("--manifest", type=Path, help="Run manifest path")
    parser.add_argument(
        "--allow-gaps",
        action="store_true",
        help="Write a draft manifest with documented gaps instead of enforcing the "
        "both-mode no-gap numeric contract; not a final hand-off.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = finalize_inputs(
            schema_path=args.schema,
            main_input_path=args.main_input,
            sources_path=args.sources,
            audit_path=args.audit,
            auto_run_log_path=args.auto_run_log,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
            require_complete=not args.allow_gaps,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}finalized {result['filled']}/{result['main_rows']} filled cell(s), "
        f"{result['shared']} shared, {result['gaps']} gap(s)"
    )
    if not args.dry_run:
        print(f"Main Input -> {result['main_output_path']}")
        print(f"Reference Values -> {result['reference_output_path']}")
        print(f"Manifest -> {result['manifest_path']}")
        if result["auto_review_path"]:
            print(f"Auto review -> {result['auto_review_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
