"""Validate one extractor JSON and append its rows to Audit.csv.

This step performs no normalization and no arithmetic. It validates entity and
parameter cells against ``tea-schema.json``, checks the scope-relevance fields,
denormalizes ``source_url`` from ``Sources.csv``, and appends Audit-shaped rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.csvio import AUDIT_FIELDNAMES, append_rows
from lib.extraction import ExtractionValidationError, extractor_doc_to_audit_rows
from lib.schema import load_schema
from lib.source_url import SourceUrlError


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return doc


def _parse_target(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError(f"expected target {value!r} to look like entity:parameter")
    entity, parameter = value.split(":", 1)
    entity = entity.strip()
    parameter = parameter.strip()
    if not entity or not parameter:
        raise ValueError(f"expected target {value!r} to include entity and parameter")
    return entity, parameter


def targets_from_manifest(manifest_path: str | Path, *, entry_id: str = "", source_key: str = "") -> list[tuple[str, str]]:
    """Return expected ``(entity, parameter)`` pairs from one manifest entry."""

    with open(manifest_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    entries = doc.get("manifest") if isinstance(doc, dict) else doc
    if not isinstance(entries, list):
        raise ValueError(f"{manifest_path}: manifest must contain a list")
    matches = []
    for entry in entries:
        if entry_id and entry.get("id") != entry_id:
            continue
        if source_key and entry.get("source_key") != source_key:
            continue
        matches.append(entry)
    if not matches:
        needle = entry_id or source_key
        raise ValueError(f"{manifest_path}: no manifest entry found for {needle!r}")
    if len(matches) > 1:
        raise ValueError(f"{manifest_path}: multiple manifest entries match; pass --entry-id")

    targets: list[tuple[str, str]] = []
    for target in matches[0].get("coverage_targets", []):
        entity = str(target.get("entity") or "").strip()
        for parameter in target.get("parameters", []):
            pid = str(parameter.get("id") if isinstance(parameter, dict) else parameter).strip()
            if entity and pid:
                targets.append((entity, pid))
    return targets


def ingest_extractor_output(
    *,
    schema_path: str | Path,
    input_path: str | Path,
    audit_path: str | Path = "Audit.csv",
    sources_path: str | Path = "Sources.csv",
    source_quality: str = "",
    expected_targets: list[tuple[str, str]] | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    doc = load_json(input_path)
    result = extractor_doc_to_audit_rows(
        doc,
        schema,
        sources_path=sources_path,
        source_quality_fallback=source_quality,
        expected_targets=expected_targets,
    )
    if not dry_run:
        append_rows(audit_path, AUDIT_FIELDNAMES, result.audit_rows)
    return {
        "rows": result.audit_rows,
        "counts": result.counts,
        "audit_path": Path(audit_path),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--input", type=Path, required=True, help="Extractor output JSON")
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit.csv to append to")
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"), help="Sources.csv for source_url")
    parser.add_argument(
        "--source-quality",
        default="",
        help="Fallback quality tag for value-bearing rows that omit quality_tag",
    )
    parser.add_argument(
        "--expected-target",
        action="append",
        default=[],
        help="Expected entity:parameter cell; repeatable",
    )
    parser.add_argument("--manifest", type=Path, help="Manifest to read expected targets from")
    parser.add_argument("--entry-id", help="Manifest entry id")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize only")
    args = parser.parse_args(argv)

    try:
        expected = [_parse_target(value) for value in args.expected_target]
        if args.manifest:
            source_key = ""
            if not args.entry_id:
                source_key = str(load_json(args.input).get("source_key") or "")
            expected.extend(
                targets_from_manifest(args.manifest, entry_id=args.entry_id or "", source_key=source_key)
            )
        result = ingest_extractor_output(
            schema_path=args.schema,
            input_path=args.input,
            audit_path=args.audit,
            sources_path=args.sources,
            source_quality=args.source_quality,
            expected_targets=expected or None,
            dry_run=args.dry_run,
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        ExtractionValidationError,
        SourceUrlError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result["counts"]
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{counts['rows']} row(s) from {args.input} "
        f"({counts['with_values']} values, {counts['not_found']} blank; "
        f"{counts['clear']} clear / {counts['hold']} hold / {counts['reject']} reject) "
        f"-> {args.audit}"
    )
    if counts["hold"]:
        print("NOTE: unresolved hold rows block normalization until Stage 3.1 is applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
