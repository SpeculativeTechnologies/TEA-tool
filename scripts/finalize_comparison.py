"""Finalize comparison-level summary artifacts from option final folders."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Mapping

from lib.consolidation import main_row_has_value
from lib.csvio import MAIN_INPUT_FIELDNAMES, read_rows, write_rows
from lib.shared_inputs import is_shared_row
from validate_comparison_project import ComparisonProjectError, load_project


SHARED_ASSUMPTION_FIELDNAMES = [
    "shared_input_id",
    "option_id",
    "entity",
    "parameter",
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "source_key",
    "source_url",
    "page_ref",
    "quality_tag",
    "notes",
]

OPTION_SUMMARY_FIELDNAMES = [
    "option_id",
    "display_name",
    "main_input_path",
    "filled_cells",
    "total_cells",
    "residual_gaps",
    "shared_cells",
    "quality_distribution",
]


def _quote(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _quality_distribution(rows: list[dict[str, str]]) -> str:
    counts: Counter = Counter()
    for row in rows:
        if not main_row_has_value(row):
            continue
        tag = (row.get("quality_tag") or "untagged").strip() or "untagged"
        counts[tag] += 1
    return "; ".join(f"{tag}={count}" for tag, count in sorted(counts.items()))


def _shared_assumption_rows(project) -> list[dict[str, str]]:
    inputs_by_id = {
        str(row.get("shared_input_id") or "").strip(): row
        for row in project.shared_inputs
    }
    sources_by_key = {
        str(row.get("source_key") or "").strip(): row
        for row in project.shared_sources
    }
    rows: list[dict[str, str]] = []
    for mapping in project.shared_mappings:
        shared = inputs_by_id[str(mapping.get("shared_input_id") or "").strip()]
        source = sources_by_key[str(shared.get("source_key") or "").strip()]
        row = {name: "" for name in SHARED_ASSUMPTION_FIELDNAMES}
        for key in ("shared_input_id", "raw_value", "raw_units", "raw_basis_scale",
                    "raw_basis_scale_units", "raw_basis_year", "source_key",
                    "page_ref", "quality_tag"):
            row[key] = str(shared.get(key) or "")
        row["source_url"] = str(source.get("source_url") or "")
        row["option_id"] = str(mapping.get("option_id") or "")
        row["entity"] = str(mapping.get("entity") or "")
        row["parameter"] = str(mapping.get("parameter") or "")
        notes = [str(shared.get("notes") or "").strip(), str(mapping.get("notes") or "").strip()]
        row["notes"] = " | ".join(note for note in notes if note)
        rows.append(row)
    return rows


def _option_main_input_path(option) -> Path:
    final = option.run_dir / "final" / "Main Input.csv"
    return final if final.exists() else option.run_dir / "Main Input.csv"


def _option_summary(option) -> dict[str, str]:
    main_input_path = _option_main_input_path(option)
    rows = read_rows(main_input_path, required_columns=MAIN_INPUT_FIELDNAMES)
    filled = sum(1 for row in rows if main_row_has_value(row))
    shared = sum(1 for row in rows if is_shared_row(row))
    out = {name: "" for name in OPTION_SUMMARY_FIELDNAMES}
    out.update(
        {
            "option_id": option.option_id,
            "display_name": option.display_name,
            "main_input_path": str(main_input_path),
            "filled_cells": str(filled),
            "total_cells": str(len(rows)),
            "residual_gaps": str(len(rows) - filled),
            "shared_cells": str(shared),
            "quality_distribution": _quality_distribution(rows),
        }
    )
    return out


def _manifest_markdown(
    *,
    frame: Mapping[str, object],
    option_summaries: list[dict[str, str]],
    shared_rows: list[dict[str, str]],
) -> str:
    lines = [
        f"# Comparison Manifest - {_quote(frame.get('display_name'))}",
        "",
        "## Summary",
        "",
        f"- Comparison ID: `{_quote(frame.get('comparison_id'))}`",
        f"- Options: {len(option_summaries)}",
        f"- Shared input mappings: {len(shared_rows)}",
        f"- Functional unit: `{_quote((frame.get('functional_unit') or {}).get('symbol') or (frame.get('functional_unit') or {}).get('name'))}`",
        "",
        "## Options",
        "",
        "| option | filled | gaps | shared | quality distribution |",
        "|---|---:|---:|---:|---|",
    ]
    for row in option_summaries:
        lines.append(
            f"| {_quote(row['option_id'])} | {_quote(row['filled_cells'])}/{_quote(row['total_cells'])} | "
            f"{_quote(row['residual_gaps'])} | {_quote(row['shared_cells'])} | "
            f"{_quote(row['quality_distribution'])} |"
        )

    headline_metrics = frame.get("headline_metrics") or []
    lines.extend(["", "## Headline Metrics", ""])
    if isinstance(headline_metrics, list) and headline_metrics:
        for metric in headline_metrics:
            lines.append(f"- `{_quote(metric)}`")
    else:
        lines.append("None declared.")
    lines.extend(["", "## Stop Point", ""])
    lines.append("Comparison finalization summarizes populated inputs only; model execution stays outside this workflow.")
    lines.append("")
    return "\n".join(lines)


def finalize_comparison(
    *,
    project_dir: str | Path = ".",
    output_dir: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    project = load_project(project_dir)
    output_dir = Path(output_dir) if output_dir is not None else project.project_dir / "final"
    shared_rows = _shared_assumption_rows(project)
    option_summaries = [_option_summary(option) for option in project.options.values()]
    manifest = _manifest_markdown(
        frame=project.frame,
        option_summaries=option_summaries,
        shared_rows=shared_rows,
    )
    shared_path = output_dir / "shared-assumptions.csv"
    summary_path = output_dir / "option-summary.csv"
    manifest_path = output_dir / "comparison-manifest.md"

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_rows(shared_path, SHARED_ASSUMPTION_FIELDNAMES, shared_rows)
        write_rows(summary_path, OPTION_SUMMARY_FIELDNAMES, option_summaries)
        manifest_path.write_text(manifest, encoding="utf-8")

    return {
        "project": project,
        "output_dir": output_dir,
        "shared_path": shared_path,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
        "shared_rows": len(shared_rows),
        "options": len(option_summaries),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path("."), help="Comparison project folder")
    parser.add_argument("--output-dir", type=Path, help="Comparison final output folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = finalize_comparison(
            project_dir=args.project_dir,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
    except (OSError, ComparisonProjectError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}finalized comparison: {result['options']} option(s), "
        f"{result['shared_rows']} shared mapping row(s)"
    )
    if not args.dry_run:
        print(f"Shared assumptions -> {result['shared_path']}")
        print(f"Option summary -> {result['summary_path']}")
        print(f"Manifest -> {result['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
