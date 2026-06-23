"""Build a resumable extraction manifest from approved search candidates.

The search lane keeps coverage in candidate JSON and accepted source metadata
in ``Sources.csv``. This script joins those two facts, finds the downloaded
source file, and emits one extraction slice per accepted source.

Example:
    python scripts/extraction_manifest.py --schema tea-schema.json \
        --input master-list.json --input gap-fill-1A.json \
        --source-dir "master list sources" --source-dir "gap fill sources" \
        --sources Sources.csv --output extractions/extraction_manifest.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from lib.csvio import read_rows
from lib.pinned import read_pinned_cells
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema
from lib.search import Candidate, SearchValidationError, source_file_present_for, validate_search_file


DEFAULT_SOURCE_DIRS = ("master list sources", "gap fill sources", "sources")


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return safe or "source"


def _quality_from_notes(notes: str) -> str:
    match = re.search(r"(?:^|[;\s])search_quality_estimate=([A-Za-z0-9_-]+)", notes or "")
    return match.group(1) if match else ""


def _source_registry(sources_path: str | Path) -> dict[str, dict[str, str]]:
    rows = read_rows(
        sources_path,
        required_columns=["source_key", "source_url", "source_role"],
        missing_ok=True,
    )
    registry: dict[str, dict[str, str]] = {}
    for row in rows:
        key = (row.get("source_key") or "").strip()
        if not key:
            continue
        role = (row.get("source_role") or "").strip().lower()
        if role and role not in {"extraction", "both"}:
            continue
        registry[key] = row
    return registry


def _candidate_map(
    schema: Schema,
    inputs: Iterable[str | Path],
) -> tuple[dict[str, Candidate], list[str]]:
    candidates: dict[str, Candidate] = {}
    duplicate_keys: list[str] = []
    for input_path in inputs:
        for candidate in validate_search_file(input_path, schema, mode="master"):
            prior = candidates.get(candidate.source_key)
            if prior and prior.raw != candidate.raw:
                duplicate_keys.append(candidate.source_key)
                continue
            candidates[candidate.source_key] = candidate
    return candidates, duplicate_keys


def _find_source_file(source_key: str, source_dirs: Iterable[str | Path]) -> Path | None:
    for source_dir in source_dirs:
        path = source_file_present_for(source_key, source_dir)
        if path is not None:
            return path
    return None


def _parameter_descriptor(schema: Schema, parameter_id: str) -> dict[str, object]:
    parameter = schema.parameter(parameter_id)
    descriptor = {
        "id": parameter_id,
        "label": parameter.get("label", parameter_id),
        "rule_type": parameter["rule_type"],
        "first_class": bool(parameter.get("first_class")),
        "context_free": bool(parameter.get("context_free")),
        "reference_value": bool(parameter.get("reference_value")),
    }
    for key in ("units", "numerator_units", "per", "canonical_unit", "basis", "market_basis",
                "capex_form", "description"):
        if parameter.get(key) not in (None, ""):
            descriptor[key] = parameter.get(key)
    return descriptor


def _coverage_targets(
    schema: Schema,
    candidate: Candidate,
    *,
    pinned_cells: set[tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    pinned_cells = pinned_cells or set()
    grouped: dict[str, list[str]] = {}
    for entity, parameter in candidate.field_coverage:
        if (entity, parameter) in pinned_cells:
            continue
        grouped.setdefault(entity, [])
        if parameter not in grouped[entity]:
            grouped[entity].append(parameter)

    targets: list[dict[str, object]] = []
    for entity, parameters in grouped.items():
        if entity == GLOBAL_ENTITY_ID:
            target = {
                "entity": GLOBAL_ENTITY_ID,
                "entity_name": "Reference values",
                "scope_frame": {
                    "in_scope": "Context-free reference value. Do not use TEA system context.",
                    "known_out_of_scope": [],
                },
            }
        else:
            ent = schema.entity(entity)
            target = {
                "entity": entity,
                "entity_name": ent.get("name", entity),
                "entity_description": ent.get("description", ""),
                "entity_output": ent.get("output", ""),
                "scope_frame": schema.scope_frame(entity) or {},
            }
        target["parameters"] = [_parameter_descriptor(schema, p) for p in parameters]
        targets.append(target)
    return targets


def build_manifest(
    *,
    schema_path: str | Path,
    inputs: Iterable[str | Path],
    sources_path: str | Path = "Sources.csv",
    source_dirs: Iterable[str | Path] = DEFAULT_SOURCE_DIRS,
    output_dir: str | Path = "extractions",
    main_input_path: str | Path | None = "Main Input.csv",
    audit_path: str | Path | None = "Audit.csv",
) -> dict[str, object]:
    """Return a manifest document without writing it."""

    schema = load_schema(schema_path)
    inputs = list(inputs)
    if not inputs:
        raise ValueError("at least one search JSON --input is required")

    candidates, duplicate_keys = _candidate_map(schema, inputs)
    if duplicate_keys:
        raise ValueError(f"duplicate source_key(s) with conflicting candidate data: {duplicate_keys!r}")

    registry = _source_registry(sources_path)
    output_dir = Path(output_dir)
    source_dirs = [Path(path) for path in source_dirs]
    pinned_cells = read_pinned_cells(main_input_path=main_input_path, audit_path=audit_path)

    entries: list[dict[str, object]] = []
    skipped_unregistered: list[str] = []
    skipped_no_file: list[str] = []
    skipped_no_candidate: list[str] = []

    for source_key in sorted(registry):
        candidate = candidates.get(source_key)
        if candidate is None:
            skipped_no_candidate.append(source_key)
            continue
        source_file = _find_source_file(source_key, source_dirs)
        if source_file is None:
            skipped_no_file.append(source_key)
            continue
        source_row = registry[source_key]
        source_url = (source_row.get("source_url") or "").strip()
        if source_url and candidate.source_url and source_url != candidate.source_url:
            raise ValueError(
                f"source_url mismatch for {source_key!r}: Sources.csv has {source_url!r}, "
                f"candidate JSON has {candidate.source_url!r}"
            )
        coverage_targets = _coverage_targets(schema, candidate, pinned_cells=pinned_cells)
        if not coverage_targets:
            continue

        entry_id = _safe_id(source_key)
        entries.append(
            {
                "id": entry_id,
                "source_key": source_key,
                "source_url": source_url or candidate.source_url,
                "source_path": str(source_file),
                "output_json": str(output_dir / f"{entry_id}.extraction.json"),
                "source_quality_estimate": (
                    candidate.quality_estimate
                    or _quality_from_notes(source_row.get("notes", ""))
                ),
                "coverage_targets": coverage_targets,
            }
        )

    registered = set(registry)
    for source_key in sorted(set(candidates) - registered):
        skipped_unregistered.append(source_key)

    return {
        "schema_tea_id": schema.tea_id,
        "schema_path": str(Path(schema_path)),
        "sources_path": str(Path(sources_path)),
        "source_dirs": [str(path) for path in source_dirs],
        "manifest": entries,
        "count": len(entries),
        "skipped": {
            "unregistered": skipped_unregistered,
            "registered_but_no_file": skipped_no_file,
            "registered_but_no_candidate": skipped_no_candidate,
            "pinned_cells": [list(cell) for cell in sorted(pinned_cells)],
        },
    }


def write_manifest(path: str | Path, manifest: dict[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--input", type=Path, action="append", default=[], help="Search JSON; repeatable")
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"), help="Accepted Sources.csv")
    parser.add_argument(
        "--source-dir",
        type=Path,
        action="append",
        default=[],
        help="Directory with approved source files; repeatable",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("extractions") / "extraction_manifest.json",
        help="Manifest JSON to write",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("extractions"),
        help="Directory named in each output_json path",
    )
    parser.add_argument(
        "--main-input",
        type=Path,
        default=Path("Main Input.csv"),
        help="Main Input CSV used to skip pinned cells",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("Audit.csv"),
        help="Audit CSV used to skip pinned cells",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    args = parser.parse_args(argv)

    source_dirs = args.source_dir or [Path(p) for p in DEFAULT_SOURCE_DIRS]
    try:
        manifest = build_manifest(
            schema_path=args.schema,
            inputs=args.input,
            sources_path=args.sources,
            source_dirs=source_dirs,
            output_dir=args.output_dir,
            main_input_path=args.main_input,
            audit_path=args.audit,
        )
    except (OSError, ValueError, SearchValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    if not args.dry_run:
        write_manifest(args.output, manifest)

    print(f"{prefix}{manifest['count']} extraction slice(s) -> {args.output}")
    skipped = manifest["skipped"]
    print(
        f"{prefix}skipped: {len(skipped['unregistered'])} unregistered, "
        f"{len(skipped['registered_but_no_file'])} no file, "
        f"{len(skipped['registered_but_no_candidate'])} no candidate coverage"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
