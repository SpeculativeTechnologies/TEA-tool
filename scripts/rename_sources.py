"""Normalize approved source filenames from a search candidate JSON.

The search agents emit candidate JSON only. After the gate reviews candidates
and accepted source files are materialized to ``master list sources/`` or
``gap fill sources/``, run this helper to match legacy or supplied filenames to
candidate metadata and rename/copy them to:

    {entity_or_chain}_{source_key}.{ext}

Examples:
    python scripts/rename_sources.py --schema tea-schema.json --input master-list.json --source-dir "master list sources"
    python scripts/rename_sources.py --schema tea-schema.json --input gap-fill-1A.json --source-dir "gap fill sources" --mode gap --entity 1A --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from lib.schema import load_schema
from lib.search import (
    SearchValidationError,
    ScoredMatch,
    best_match_for_file,
    discover_files,
    profile_file,
    resolve_matches,
    target_path_for,
    validate_search_file,
)


def perform_match(
    match: ScoredMatch,
    source_dir: Path,
    prefix_mode: str,
    *,
    action: str,
    apply: bool,
) -> str:
    """Rename/copy one selected match, or describe the dry-run operation."""

    target = target_path_for(match, source_dir, prefix_mode)
    source_resolved = match.path.resolve()
    target_resolved = target.resolve()

    if source_resolved == target_resolved:
        return f"ok already named: {match.path.name}"
    if target.exists():
        return f"skip target exists: {match.path.name} -> {target.name}"

    verb = "rename" if action == "rename" else "copy"
    if not apply:
        return f"dry-run {verb}: {match.path.name} -> {target.name}"

    if action == "rename":
        match.path.rename(target)
    else:
        shutil.copy2(match.path, target)
    return f"{verb}d: {match.path.name} -> {target.name}"


def rename_sources(
    *,
    schema_path: str | Path,
    input_path: str | Path,
    source_dir: str | Path,
    mode: str = "master",
    entity_id: str | None = None,
    uncovered_parameters: list[str] | None = None,
    approved_source_keys: list[str] | None = None,
    prefix_mode: str = "auto",
    action: str = "rename",
    apply: bool = False,
    min_score: int = 55,
    max_pages: int = 6,
) -> dict[str, object]:
    """Match materialized source files and optionally normalize filenames."""

    schema = load_schema(schema_path)
    candidates = validate_search_file(
        input_path,
        schema,
        mode=mode,
        entity_id=entity_id,
        uncovered_parameters=uncovered_parameters or [],
        approved_source_keys=approved_source_keys or [],
    )
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    files = discover_files(source_dir)
    profiles = [profile_file(path, max_pages=max_pages) for path in files]

    proposed: list[ScoredMatch] = []
    unmatched: list[Path] = []
    warnings: list[str] = []
    for profile in profiles:
        warnings.extend(profile.warnings)
        match = best_match_for_file(profile, candidates, min_score)
        if match is None:
            unmatched.append(profile.path)
        else:
            proposed.append(match)

    selected, duplicate_matches = resolve_matches(proposed)
    actions = [
        perform_match(
            match,
            source_dir,
            prefix_mode,
            action=action,
            apply=apply,
        )
        for match in selected
    ]
    return {
        "candidates": candidates,
        "files": files,
        "selected": selected,
        "duplicate_matches": duplicate_matches,
        "unmatched": unmatched,
        "warnings": warnings,
        "actions": actions,
    }


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument("--input", type=Path, required=True, help="Master-list or gap-fill JSON")
    parser.add_argument("--source-dir", type=Path, required=True, help="Folder with materialized source files")
    parser.add_argument("--mode", choices=("master", "gap"), default="master")
    parser.add_argument("--entity", dest="entity_id", help="Target entity id for gap mode")
    parser.add_argument(
        "--uncovered-parameters",
        help="Comma-separated parameter ids that this gap-fill run is allowed to cover",
    )
    parser.add_argument(
        "--approved-source-keys",
        help="Comma-separated master-list source keys already approved (gap mode duplicate guard)",
    )
    parser.add_argument(
        "--prefix-mode",
        choices=("auto", "chain", "primary-entity"),
        default="auto",
        help="Filename prefix strategy before _source_key",
    )
    parser.add_argument("--action", choices=("rename", "copy"), default="rename")
    parser.add_argument("--apply", action="store_true", help="Actually perform file operations")
    parser.add_argument("--min-score", type=int, default=55, help="Minimum match score")
    parser.add_argument("--max-pages", type=int, default=6, help="PDF front pages to inspect")
    args = parser.parse_args(argv)

    try:
        result = rename_sources(
            schema_path=args.schema,
            input_path=args.input,
            source_dir=args.source_dir,
            mode=args.mode,
            entity_id=args.entity_id,
            uncovered_parameters=_split_csv(args.uncovered_parameters),
            approved_source_keys=_split_csv(args.approved_source_keys),
            prefix_mode=args.prefix_mode,
            action=args.action,
            apply=args.apply,
            min_score=args.min_score,
            max_pages=args.max_pages,
        )
    except (FileNotFoundError, SearchValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for warning in result["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)

    files = result["files"]
    selected = result["selected"]
    print(
        f"Matched {len(selected)} of {len(files)} supported file(s) "
        f"against {len(result['candidates'])} candidate(s)."
    )
    if not args.apply:
        print("Dry run only. Re-run with --apply to perform file operations.")

    for match, action_result in zip(selected, result["actions"]):
        print(
            f"{action_result}  [score={match.score}; "
            f"source_key={match.candidate.source_key}; {match.details}]"
        )

    if result["duplicate_matches"]:
        print("\nDuplicate/lower-ranked matches ignored:")
        for match in result["duplicate_matches"]:
            print(
                f"  {match.path.name} -> {match.candidate.source_key} "
                f"[score={match.score}; {match.details}]"
            )

    if result["unmatched"]:
        print("\nNo confident match:")
        for path in result["unmatched"]:
            print(f"  {path.name}")

    matched_keys = {match.candidate.source_key for match in selected}
    missing_keys = [
        candidate.source_key
        for candidate in result["candidates"]
        if candidate.source_key not in matched_keys
    ]
    if missing_keys:
        print("\nCandidates without a matched source file:")
        for key in missing_keys:
            print(f"  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
