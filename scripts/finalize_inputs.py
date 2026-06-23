"""Finalize a run after consolidation without running a model.

Phase 7.1 emits the final Main Input table, a Reference Values table, and a
run manifest summarizing coverage, quality distribution, source counts, pinned
cells, residual gaps, and declared validation targets.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Mapping

from lib.consolidation import main_row_has_value
from lib.csvio import MAIN_INPUT_FIELDNAMES, SOURCES_FIELDNAMES, read_rows, write_rows
from lib.pinned import cell_key, is_pinned_row
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


def _pinned_rows(main_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in main_rows if is_pinned_row(row)]


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
    pinned = _pinned_rows(main_rows)
    source_counts = _source_counts(sources_rows)
    quality_counts = _quality_distribution(main_rows)
    validation_targets = _validation_targets(schema)

    lines = [
        f"# Run Manifest - {schema.display_name}",
        "",
        "## Summary",
        "",
        f"- TEA ID: `{schema.tea_id}`",
        f"- Functional unit: `{schema.functional_unit_symbol or schema.functional_unit_name}`",
        f"- Basis: `{schema.currency}`, `{schema.base_year}`, `{schema.inflation_index}`",
        f"- Main Input: `{main_output_path}`",
        f"- Reference Values: `{reference_output_path}`",
        f"- Coverage: {len(filled)}/{len(main_rows)} filled; {len(gaps)} residual gap(s)",
        f"- Pinned cells: {len(pinned)}",
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

    lines.extend(["", "## Pinned Cells", ""])
    if pinned:
        lines.extend(["| entity | parameter | source_key | source_url |", "|---|---|---|---|"])
        for row in pinned:
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
            "## Stop Point",
            "",
            "This tool stops at populated inputs. The analyst runs their own model outside this workflow.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_inputs(
    *,
    schema_path: str | Path,
    main_input_path: str | Path = "Main Input.csv",
    sources_path: str | Path = "Sources.csv",
    output_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Finalize Main Input and write reference values plus run manifest."""

    schema = load_schema(schema_path)
    main_input_path = Path(main_input_path)
    sources_path = Path(sources_path)
    output_dir = Path(output_dir) if output_dir is not None else main_input_path.parent
    manifest_path = (
        Path(manifest_path) if manifest_path is not None else output_dir / "run-manifest.md"
    )
    main_output_path = output_dir / "Main Input.csv"
    reference_output_path = output_dir / "Reference Values.csv"

    main_rows = read_rows(main_input_path, required_columns=MAIN_INPUT_FIELDNAMES)
    _validate_main_input(main_rows, schema)
    sources_rows = read_rows(sources_path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)
    reference_rows = [row for row in main_rows if row.get("entity") == GLOBAL_ENTITY_ID]
    manifest = _manifest_markdown(
        schema=schema,
        main_rows=main_rows,
        sources_rows=sources_rows,
        main_output_path=main_output_path,
        reference_output_path=reference_output_path,
    )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        if main_input_path.resolve() != main_output_path.resolve():
            shutil.copyfile(main_input_path, main_output_path)
        write_rows(reference_output_path, MAIN_INPUT_FIELDNAMES, reference_rows)
        manifest_path.write_text(manifest, encoding="utf-8")

    gaps = _gap_rows(main_rows)
    pinned = _pinned_rows(main_rows)
    return {
        "schema": schema,
        "main_input_path": main_input_path,
        "main_output_path": main_output_path,
        "reference_output_path": reference_output_path,
        "manifest_path": manifest_path,
        "main_rows": len(main_rows),
        "filled": len(main_rows) - len(gaps),
        "gaps": len(gaps),
        "pinned": len(pinned),
        "reference_rows": len(reference_rows),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--main-input", type=Path, default=Path("Main Input.csv"))
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"))
    parser.add_argument("--output-dir", type=Path, help="Directory for final artifacts")
    parser.add_argument("--manifest", type=Path, help="Run manifest path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = finalize_inputs(
            schema_path=args.schema,
            main_input_path=args.main_input,
            sources_path=args.sources,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}finalized {result['filled']}/{result['main_rows']} filled cell(s), "
        f"{result['pinned']} pinned, {result['gaps']} gap(s)"
    )
    if not args.dry_run:
        print(f"Main Input -> {result['main_output_path']}")
        print(f"Reference Values -> {result['reference_output_path']}")
        print(f"Manifest -> {result['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
