"""Print the next pending extraction batch from a manifest.

Extraction is one agent invocation per manifest entry. A slice is complete when
its ``output_json`` exists and is non-empty, so this script is safe to re-run
after interruptions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.schema import load_schema


def load_manifest(path: str | Path) -> list[dict]:
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    entries = doc.get("manifest") if isinstance(doc, dict) else doc
    if not isinstance(entries, list):
        raise ValueError(f"{path}: manifest must be a list or object with manifest list")
    return entries


def output_path(entry: dict, manifest_path: str | Path) -> Path:
    del manifest_path
    raw = Path(str(entry.get("output_json") or ""))
    return raw


def is_done(entry: dict, manifest_path: str | Path) -> bool:
    out = output_path(entry, manifest_path)
    return out.exists() and out.stat().st_size > 0


def pending_entries(manifest_path: str | Path) -> tuple[list[dict], list[dict]]:
    entries = load_manifest(manifest_path)
    done = [entry for entry in entries if is_done(entry, manifest_path)]
    pending = [entry for entry in entries if not is_done(entry, manifest_path)]
    return done, pending


def next_batch(manifest_path: str | Path, *, batch_size: int) -> list[dict]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    _done, pending = pending_entries(manifest_path)
    return pending[:batch_size]


def _target_summary(entry: dict) -> str:
    pieces: list[str] = []
    for target in entry.get("coverage_targets", []):
        params = target.get("parameters") or []
        pieces.append(f"{target.get('entity')}[{len(params)}p]")
    return ", ".join(pieces)


def _default_batch_size(manifest_path: Path) -> int:
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        schema_path = doc.get("schema_path") if isinstance(doc, dict) else None
        if schema_path:
            path = Path(schema_path)
            if not path.is_absolute():
                path = manifest_path.parent / path
            return load_schema(path).extraction_batch_size
    except Exception:
        pass
    return 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("extractions") / "extraction_manifest.json",
        help="Extraction manifest JSON",
    )
    parser.add_argument("--batch-size", type=int, help="Max slices to return")
    parser.add_argument("--all", action="store_true", help="Show all pending slices")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        batch_size = args.batch_size or _default_batch_size(args.manifest)
        done, pending = pending_entries(args.manifest)
        batch = pending if args.all else pending[:batch_size]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(batch, indent=2))
        return 0

    print(f"Extraction manifest: {args.manifest}")
    print(f"  done    : {len(done)}")
    print(f"  pending : {len(pending)}")
    if not pending:
        print("All extraction slices are complete. Next: ingest outputs and sweep holds.")
        return 0

    label = "ALL PENDING" if args.all else "NEXT BATCH"
    print(f"\n{label}: {len(batch)} slice(s)")
    for entry in batch:
        print(f"  {entry.get('id')}")
        print(f"      source : {entry.get('source_path')}")
        print(f"      output : {entry.get('output_json')}")
        print(
            f"      quality: {entry.get('source_quality_estimate', '') or '?'}   "
            f"coverage: {_target_summary(entry)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
