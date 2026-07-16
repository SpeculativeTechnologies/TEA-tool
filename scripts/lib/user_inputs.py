"""Analyst-supplied inputs: validate and materialize user values.

The orchestrator lets an analyst supply values directly — conversational
submissions, uploaded-document values the user wants to fix, or shared
assumptions. Those land in two run-local CSVs (orchestrator §6):

- ``user-sources.csv`` — the source-registry shape (``Sources.csv`` columns),
  which may carry ``source_role=analyst`` for a synthetic conversational batch.
- ``user-inputs.csv`` — only values the analyst mapped to a real schema cell.

Materialization is deterministic and idempotent: it merges user sources into
the run ``Sources.csv`` and appends one Audit row per user input (tagged with a
``user_input_id=`` marker so a rerun replaces prior user rows without touching
extracted/estimated/shared rows). Each materialized row carries:

- ``input_origin`` from the user input (``analyst`` for a direct assertion,
  ``extracted`` when the user is fixing a value an uploaded doc reported, or
  ``shared``);
- ``input_priority=fixed`` when the user fixed it as authoritative, else blank;
- ``relevance_status=clear`` and the denormalized ``source_url``.

The normal normalize/consolidate pipeline then handles them, with fixed inputs
winning selection (see ``consolidation.select_rows``). A non-fixed analyst row
is candidate evidence: it never suppresses research and never displaces a
better-quality candidate on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from .csvio import (
    AUDIT_FIELDNAMES,
    SOURCES_FIELDNAMES,
    USER_INPUTS_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from .schema import Schema, load_schema
from .shared_inputs import (
    ANALYST_ORIGIN,
    EXTRACTED_ORIGIN,
    FIXED_PRIORITY,
    SHARED_ORIGIN,
    cell_key,
    validate_cell,
)

#: Notes marker that identifies an Audit row materialized from user-inputs.csv.
USER_INPUT_MARKER = "user_input_id="

#: Lanes a user input may declare. ``analyst`` is a direct assertion or model
#: assumption; ``extracted`` fixes a value an uploaded third-party doc reported
#: (origin preserved); ``shared`` is a fixed shared assumption.
ALLOWED_USER_ORIGINS = {ANALYST_ORIGIN, EXTRACTED_ORIGIN, SHARED_ORIGIN}

_TRUTHY = {"true", "t", "yes", "y", "1", "fixed"}
_FALSY = {"", "false", "f", "no", "n", "0", "blank"}

_AUDIT_COPY_FIELDS = (
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "page_ref",
    "quality_tag",
)


class UserInputError(ValueError):
    """Raised when analyst-supplied inputs violate the contract."""


def is_fixed_flag(value: object) -> bool:
    """Parse a ``fixed`` cell into a boolean, rejecting unrecognized text."""

    token = str(value or "").strip().lower()
    if token in _TRUTHY:
        return True
    if token in _FALSY:
        return False
    raise UserInputError(f"fixed must be TRUE or blank, not {value!r}")


def read_user_sources(path: str | Path) -> list[dict[str, str]]:
    return read_rows(path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)


def read_user_inputs(path: str | Path) -> list[dict[str, str]]:
    return read_rows(path, required_columns=USER_INPUTS_FIELDNAMES, missing_ok=True)


def validate_user_sources(rows: list[dict[str, str]]) -> list[str]:
    """Validate user-sources.csv; permits ``source_role=analyst``."""

    errors: list[str] = []
    seen: dict[str, int] = {}
    for idx, row in enumerate(rows, start=2):
        key = str(row.get("source_key") or "").strip()
        if not key:
            errors.append(f"user-sources.csv row {idx}: source_key is required")
            continue
        if key in seen:
            errors.append(
                f"user-sources.csv row {idx}: duplicate source_key {key!r}; "
                f"first seen on row {seen[key]}"
            )
        else:
            seen[key] = idx
        if not str(row.get("source_url") or "").strip():
            errors.append(f"user-sources.csv row {idx}: source_url is required")
        role = str(row.get("source_role") or "").strip().lower()
        if role and role not in {"extraction", "estimate", "both", "analyst"}:
            errors.append(
                f"user-sources.csv row {idx}: source_role {role!r} must be "
                "extraction, estimate, both, or analyst"
            )
    return errors


def validate_user_inputs(
    rows: list[dict[str, str]],
    schema: Schema,
    *,
    known_source_keys: Iterable[str],
    registered_material_tokens: Iterable[str] = (),
    source_urls: Mapping[str, str] | None = None,
) -> list[str]:
    """Validate user-inputs.csv against an option schema and known sources."""

    errors: list[str] = []
    known = {str(key).strip() for key in known_source_keys if str(key).strip()}
    quality_tags = {str(tag).strip().upper() for tag in schema.quality_tags}
    material_tokens = {
        str(token).strip().lower()
        for token in registered_material_tokens
        if str(token).strip()
    }
    urls = source_urls or {}
    seen_ids: dict[str, int] = {}

    for idx, row in enumerate(rows, start=2):
        label = f"user-inputs.csv row {idx}"
        input_id = str(row.get("input_id") or "").strip()
        if not input_id:
            errors.append(f"{label}: input_id is required")
        elif input_id in seen_ids:
            errors.append(
                f"{label}: duplicate input_id {input_id!r}; first seen on row {seen_ids[input_id]}"
            )
        else:
            seen_ids[input_id] = idx

        entity = str(row.get("entity") or "").strip()
        parameter = str(row.get("parameter") or "").strip()
        try:
            validate_cell(schema, entity, parameter, row_label=label)
        except ValueError as exc:
            errors.append(str(exc))

        if not str(row.get("raw_value") or "").strip():
            errors.append(f"{label}: raw_value is required")

        origin = str(row.get("input_origin") or "").strip().lower() or ANALYST_ORIGIN
        if origin not in ALLOWED_USER_ORIGINS:
            errors.append(
                f"{label}: input_origin {origin!r} must be one of {sorted(ALLOWED_USER_ORIGINS)}"
            )

        try:
            is_fixed_flag(row.get("fixed"))
        except UserInputError as exc:
            errors.append(f"{label}: {exc}")

        tag = str(row.get("quality_tag") or "").strip().upper()
        if tag and tag not in quality_tags:
            errors.append(f"{label}: quality_tag {tag!r} is not one of {sorted(quality_tags)}")
        if tag in {"E", "U"}:
            errors.append(
                f"{label}: quality_tag {tag!r} is reserved for Phase 6 estimation; "
                "do not materialize estimates as user inputs"
            )

        source_key = str(row.get("source_key") or "").strip()
        if not source_key:
            errors.append(f"{label}: source_key is required")
        elif source_key not in known:
            errors.append(
                f"{label}: source_key {source_key!r} is not in user-sources.csv or Sources.csv"
            )
        if origin == EXTRACTED_ORIGIN and source_key in known:
            source_url = str(urls.get(source_key) or "").strip().lower()
            if not material_tokens or not any(
                token == source_url or token in source_url for token in material_tokens
            ):
                errors.append(
                    f"{label}: input_origin 'extracted' is only for registered user-supplied "
                    "materials; web research must enter through the screener/extractor lane"
                )

    return errors


def find_fixed_conflicts(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Find cells with two or more disagreeing fixed user inputs.

    Conflicts are detected up front (both modes) so the orchestrator can raise a
    blocking issue before materialization rather than discovering it at
    consolidation.
    """

    by_cell: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        try:
            fixed = is_fixed_flag(row.get("fixed"))
        except UserInputError:
            continue
        if fixed:
            by_cell.setdefault(cell_key(row), []).append(row)

    conflicts: list[dict[str, object]] = []
    for key, members in sorted(by_cell.items()):
        signatures = {
            (
                str(row.get("raw_value") or "").strip(),
                str(row.get("raw_units") or "").strip(),
            )
            for row in members
        }
        if len(signatures) > 1:
            conflicts.append(
                {
                    "key": key,
                    "input_ids": [str(row.get("input_id") or "").strip() for row in members],
                    "values": "; ".join(
                        f"{(row.get('input_id') or 'unknown')}="
                        f"{(row.get('raw_value') or '').strip()} {(row.get('raw_units') or '').strip()}".strip()
                        for row in members
                    ),
                }
            )
    return conflicts


def format_fixed_conflict_error(conflicts: list[dict[str, object]]) -> str:
    lines = []
    for conflict in conflicts[:10]:
        entity, parameter = conflict["key"]
        lines.append(f"({entity},{parameter}): {conflict['values']}")
    more = "" if len(conflicts) <= 10 else f"\n  ... +{len(conflicts) - 10} more"
    return (
        f"{len(conflicts)} cell(s) have two or more disagreeing fixed user inputs. "
        "A fixed input is an authoritative user decision; the user must choose one "
        "value (raise a blocking issue) before materialization.\n  "
        + "\n  ".join(lines)
        + more
    )


def _merge_sources(
    existing: list[dict[str, str]],
    user_sources: list[dict[str, str]],
) -> list[dict[str, str]]:
    by_key: dict[str, dict[str, str]] = {
        str(row.get("source_key") or "").strip(): dict(row)
        for row in existing
        if str(row.get("source_key") or "").strip()
    }
    for source in user_sources:
        key = str(source.get("source_key") or "").strip()
        if not key:
            continue
        prior = by_key.get(key)
        if prior is None:
            by_key[key] = dict(source)
            continue
        prior_url = str(prior.get("source_url") or "").strip()
        new_url = str(source.get("source_url") or "").strip()
        if prior_url and new_url and prior_url != new_url:
            raise UserInputError(
                f"source_key {key!r} has a conflicting source_url in Sources.csv vs user-sources.csv"
            )
        merged = dict(prior)
        for field in SOURCES_FIELDNAMES:
            if not merged.get(field) and source.get(field):
                merged[field] = source[field]
        by_key[key] = merged
    return [by_key[key] for key in sorted(by_key)]


def _registered_material_tokens(run_dir: Path) -> set[str]:
    """Return stable URL/path tokens from ``provided-materials.json``."""

    path = run_dir / "provided-materials.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    tokens: set[str] = set()
    for material in data.get("materials", []):
        if not isinstance(material, Mapping):
            continue
        for field in ("original", "copied_to"):
            value = str(material.get(field) or "").strip().lower()
            if not value:
                continue
            tokens.add(value)
            tokens.add(Path(value).name)
    return {token for token in tokens if token}


def _audit_row_for(
    user_input: Mapping[str, str],
    *,
    source_url: str,
) -> dict[str, str]:
    row = blank_row(AUDIT_FIELDNAMES)
    row["entity"] = str(user_input.get("entity") or "").strip()
    row["parameter"] = str(user_input.get("parameter") or "").strip()
    row["source_key"] = str(user_input.get("source_key") or "").strip()
    row["source_url"] = source_url
    for field in _AUDIT_COPY_FIELDS:
        row[field] = str(user_input.get(field) or "").strip()
    row["relevance_status"] = "clear"
    row["input_origin"] = str(user_input.get("input_origin") or "").strip().lower() or ANALYST_ORIGIN
    row["input_priority"] = FIXED_PRIORITY if is_fixed_flag(user_input.get("fixed")) else ""
    input_id = str(user_input.get("input_id") or "").strip()
    note_parts = [
        f"{USER_INPUT_MARKER}{input_id}",
        str(user_input.get("notes") or "").strip(),
        (
            f"user_rationale: {str(user_input.get('user_rationale') or '').strip()}"
            if str(user_input.get("user_rationale") or "").strip()
            else ""
        ),
    ]
    row["notes"] = " | ".join(part for part in note_parts if part)
    return row


def materialize_user_inputs(
    *,
    schema_path: str | Path,
    run_dir: str | Path,
    dry_run: bool = False,
) -> dict[str, object]:
    """Validate and materialize a run's user inputs into Audit.csv + Sources.csv."""

    run_dir = Path(run_dir)
    schema = load_schema(schema_path)
    sources_path = run_dir / "Sources.csv"
    audit_path = run_dir / "Audit.csv"

    user_sources = read_user_sources(run_dir / "user-sources.csv")
    user_inputs = read_user_inputs(run_dir / "user-inputs.csv")
    existing_sources = read_rows(sources_path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)

    errors = validate_user_sources(user_sources)
    known_keys = {str(r.get("source_key") or "").strip() for r in (user_sources + existing_sources)}
    source_urls = {
        str(row.get("source_key") or "").strip(): str(row.get("source_url") or "").strip()
        for row in (user_sources + existing_sources)
    }
    errors += validate_user_inputs(
        user_inputs,
        schema,
        known_source_keys=known_keys,
        registered_material_tokens=_registered_material_tokens(run_dir),
        source_urls=source_urls,
    )
    if errors:
        raise UserInputError("\n".join(errors))

    conflicts = find_fixed_conflicts(user_inputs)
    if conflicts:
        raise UserInputError(format_fixed_conflict_error(conflicts))

    merged_sources = _merge_sources(existing_sources, user_sources)
    url_by_key = {
        str(row.get("source_key") or "").strip(): str(row.get("source_url") or "").strip()
        for row in merged_sources
    }

    new_audit_rows = [
        _audit_row_for(user_input, source_url=url_by_key.get(str(user_input.get("source_key") or "").strip(), ""))
        for user_input in user_inputs
    ]

    existing_audit = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
    retained_audit = [
        dict(row) for row in existing_audit if USER_INPUT_MARKER not in str(row.get("notes") or "")
    ]
    merged_audit = retained_audit + new_audit_rows

    fixed_count = sum(1 for row in new_audit_rows if row["input_priority"] == FIXED_PRIORITY)

    if not dry_run:
        write_rows(sources_path, SOURCES_FIELDNAMES, merged_sources)
        write_rows(audit_path, AUDIT_FIELDNAMES, merged_audit)

    return {
        "run_dir": run_dir,
        "inputs": len(new_audit_rows),
        "fixed": fixed_count,
        "sources": len(user_sources),
        "audit_rows": len(merged_audit),
        "dry_run": dry_run,
    }
