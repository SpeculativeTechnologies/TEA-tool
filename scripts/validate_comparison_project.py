"""Validate a comparison project wrapper around normal TEA option runs.

Expected project layout:

    comparison-frame.json
    shared-sources.csv
    shared-inputs.csv
    shared-input-mappings.csv
    options/<option_id>/tea-schema.json

The frame is intentionally small. Each option keeps its own normal
``tea-schema.json`` and working CSVs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from lib.csvio import (
    SHARED_INPUTS_FIELDNAMES,
    SHARED_INPUT_MAPPINGS_FIELDNAMES,
    SOURCES_FIELDNAMES,
    read_rows,
)
from lib.schema import Schema, load_schema
from lib.shared_inputs import validate_cell


class ComparisonProjectError(ValueError):
    """Raised when a comparison project contract is invalid."""


@dataclass(frozen=True)
class ComparisonOption:
    option_id: str
    display_name: str
    run_dir: Path
    schema_path: Path
    schema: Schema


@dataclass(frozen=True)
class ComparisonProject:
    project_dir: Path
    frame_path: Path
    frame: dict
    options: dict[str, ComparisonOption]
    shared_sources_path: Path
    shared_inputs_path: Path
    shared_mappings_path: Path
    shared_sources: list[dict[str, str]]
    shared_inputs: list[dict[str, str]]
    shared_mappings: list[dict[str, str]]


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise ComparisonProjectError(f"missing comparison frame: {path}") from None
    except json.JSONDecodeError as exc:
        raise ComparisonProjectError(f"{path}: invalid JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise ComparisonProjectError(f"{path}: top-level JSON must be an object")
    return doc


def _as_project_path(project_dir: Path, value: object, *, label: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ComparisonProjectError(f"{label} is required")
    path = Path(text)
    if not path.is_absolute():
        path = project_dir / path
    return path


def _required_str(obj: Mapping[str, object], key: str, *, label: str) -> str:
    value = str(obj.get(key) or "").strip()
    if not value:
        raise ComparisonProjectError(f"{label}: {key} is required")
    return value


def _validate_frame_shape(frame: Mapping[str, object]) -> None:
    for key in ("comparison_id", "display_name", "functional_unit", "basis", "options"):
        if key not in frame:
            raise ComparisonProjectError(f"comparison-frame.json: missing {key!r}")
    if not isinstance(frame.get("functional_unit"), dict):
        raise ComparisonProjectError("comparison-frame.json: functional_unit must be an object")
    if not isinstance(frame.get("basis"), dict):
        raise ComparisonProjectError("comparison-frame.json: basis must be an object")
    options = frame.get("options")
    if not isinstance(options, list) or not options:
        raise ComparisonProjectError("comparison-frame.json: options must be a non-empty list")
    for idx, option in enumerate(options):
        if not isinstance(option, dict):
            raise ComparisonProjectError(f"comparison-frame.json options[{idx}] must be an object")
        for key in ("option_id", "display_name", "run_dir", "schema_path"):
            _required_str(option, key, label=f"comparison-frame.json options[{idx}]")


def _same_basis(frame: Mapping[str, object], schema: Schema, option_id: str) -> list[str]:
    errors: list[str] = []
    frame_fu = frame["functional_unit"]
    if schema.functional_unit != frame_fu:
        errors.append(
            f"option {option_id!r}: functional_unit does not match comparison frame"
        )
    frame_basis = frame["basis"]
    for key in ("currency", "base_year", "inflation_index", "geography"):
        if schema.basis.get(key) != frame_basis.get(key):
            errors.append(f"option {option_id!r}: basis.{key} does not match comparison frame")
    return errors


def _load_options(project_dir: Path, frame: Mapping[str, object]) -> dict[str, ComparisonOption]:
    options: dict[str, ComparisonOption] = {}
    errors: list[str] = []
    for idx, option in enumerate(frame["options"]):
        option_id = _required_str(option, "option_id", label=f"options[{idx}]")
        if option_id in options:
            errors.append(f"duplicate option_id {option_id!r}")
            continue
        run_dir = _as_project_path(project_dir, option["run_dir"], label=f"options[{idx}].run_dir")
        schema_path = _as_project_path(
            project_dir,
            option["schema_path"],
            label=f"options[{idx}].schema_path",
        )
        try:
            schema = load_schema(schema_path)
        except Exception as exc:
            errors.append(f"option {option_id!r}: {exc}")
            continue
        errors.extend(_same_basis(frame, schema, option_id))
        options[option_id] = ComparisonOption(
            option_id=option_id,
            display_name=_required_str(option, "display_name", label=f"options[{idx}]"),
            run_dir=run_dir,
            schema_path=schema_path,
            schema=schema,
        )
    if errors:
        raise ComparisonProjectError("\n".join(errors))
    return options


def _ensure_unique(rows: list[dict[str, str]], key: str, *, label: str) -> None:
    seen: dict[str, int] = {}
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        value = str(row.get(key) or "").strip()
        if not value:
            errors.append(f"{label} row {idx}: {key} is required")
            continue
        if value in seen:
            errors.append(f"{label} row {idx}: duplicate {key} {value!r}; first seen on row {seen[value]}")
        else:
            seen[value] = idx
    if errors:
        raise ComparisonProjectError("\n".join(errors))


def _validate_shared_rows(
    *,
    options: dict[str, ComparisonOption],
    shared_sources: list[dict[str, str]],
    shared_inputs: list[dict[str, str]],
    shared_mappings: list[dict[str, str]],
) -> None:
    errors: list[str] = []
    source_keys = {str(row.get("source_key") or "").strip() for row in shared_sources}
    source_keys.discard("")
    input_by_id = {str(row.get("shared_input_id") or "").strip(): row for row in shared_inputs}

    for idx, row in enumerate(shared_sources, start=2):
        source_key = str(row.get("source_key") or "").strip()
        if source_key and not str(row.get("source_url") or "").strip():
            errors.append(f"shared-sources.csv row {idx}: source_url is required")

    for idx, row in enumerate(shared_inputs, start=2):
        shared_id = str(row.get("shared_input_id") or "").strip()
        source_key = str(row.get("source_key") or "").strip()
        if not shared_id:
            continue
        for key in ("raw_value", "raw_units", "source_key"):
            if not str(row.get(key) or "").strip():
                errors.append(f"shared-inputs.csv row {idx}: {key} is required")
        if source_key and source_key not in source_keys:
            errors.append(
                f"shared-inputs.csv row {idx}: source_key {source_key!r} is not in shared-sources.csv"
            )
        tag = str(row.get("quality_tag") or "").strip().upper()
        if tag in {"E", "U"}:
            errors.append(
                f"shared-inputs.csv row {idx}: quality_tag {tag!r} is reserved for "
                "per-option Phase 6 estimation; do not pre-populate comparison estimates"
            )

    seen_mappings: dict[tuple[str, str, str], int] = {}
    for idx, row in enumerate(shared_mappings, start=2):
        shared_id = str(row.get("shared_input_id") or "").strip()
        option_id = str(row.get("option_id") or "").strip()
        entity = str(row.get("entity") or "").strip()
        parameter = str(row.get("parameter") or "").strip()
        if not shared_id:
            errors.append(f"shared-input-mappings.csv row {idx}: shared_input_id is required")
            continue
        if shared_id not in input_by_id:
            errors.append(
                f"shared-input-mappings.csv row {idx}: unknown shared_input_id {shared_id!r}"
            )
            continue
        option = options.get(option_id)
        if option is None:
            errors.append(f"shared-input-mappings.csv row {idx}: unknown option_id {option_id!r}")
            continue
        key = (option_id, entity, parameter)
        if key in seen_mappings:
            errors.append(
                f"shared-input-mappings.csv row {idx}: duplicate target ({option_id},{entity},{parameter}); "
                f"first seen on row {seen_mappings[key]}"
            )
        else:
            seen_mappings[key] = idx
        try:
            validate_cell(option.schema, entity, parameter, row_label=f"shared-input-mappings.csv row {idx}")
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ComparisonProjectError("\n".join(errors))


def load_project(project_dir: str | Path = ".") -> ComparisonProject:
    project_dir = Path(project_dir).resolve()
    frame_path = project_dir / "comparison-frame.json"
    frame = _load_json(frame_path)
    _validate_frame_shape(frame)
    options = _load_options(project_dir, frame)

    shared_sources_path = project_dir / "shared-sources.csv"
    shared_inputs_path = project_dir / "shared-inputs.csv"
    shared_mappings_path = project_dir / "shared-input-mappings.csv"
    shared_sources = read_rows(shared_sources_path, required_columns=SOURCES_FIELDNAMES)
    shared_inputs = read_rows(shared_inputs_path, required_columns=SHARED_INPUTS_FIELDNAMES)
    shared_mappings = read_rows(
        shared_mappings_path,
        required_columns=SHARED_INPUT_MAPPINGS_FIELDNAMES,
    )

    _ensure_unique(shared_sources, "source_key", label="shared-sources.csv")
    _ensure_unique(shared_inputs, "shared_input_id", label="shared-inputs.csv")
    _validate_shared_rows(
        options=options,
        shared_sources=shared_sources,
        shared_inputs=shared_inputs,
        shared_mappings=shared_mappings,
    )

    return ComparisonProject(
        project_dir=project_dir,
        frame_path=frame_path,
        frame=frame,
        options=options,
        shared_sources_path=shared_sources_path,
        shared_inputs_path=shared_inputs_path,
        shared_mappings_path=shared_mappings_path,
        shared_sources=shared_sources,
        shared_inputs=shared_inputs,
        shared_mappings=shared_mappings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path("."), help="Comparison project folder")
    args = parser.parse_args(argv)

    try:
        project = load_project(args.project_dir)
    except (OSError, ComparisonProjectError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"valid comparison project {project.frame['comparison_id']!r}: "
        f"{len(project.options)} option(s), {len(project.shared_inputs)} shared input(s), "
        f"{len(project.shared_mappings)} mapping(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
