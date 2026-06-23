"""Build the Phase 6 estimation manifest from currently blank schema cells.

The manifest is deliberately schema-shaped: entities, parameters, route policy,
and the comparable rubric all come from ``tea-schema.json``. A cell is queued
when it is in the schema skeleton but has no selected real row and no prior
E-quality estimate, unless ``--force-refresh`` is used to refresh prior E rows.

Examples:
    python scripts/build_estimation_manifest.py --schema tea-schema.json
    python scripts/build_estimation_manifest.py --schema tea-schema.json --audit Audit_normalized_consolidated.csv --main-input "Main Input.csv"
    python scripts/build_estimation_manifest.py --schema tea-schema.json --force-refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from lib.csvio import AUDIT_FIELDNAMES, MAIN_INPUT_FIELDNAMES, read_rows
from lib.extraction import is_nullish
from lib.pinned import is_pinned_row, truthy as _truthy
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema


ESTIMATE_QUALITY_TAG = "E"
ANCHOR_EXCLUDED_TAGS = {"D", "E"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag(row: Mapping[str, object]) -> str:
    return str(row.get("quality_tag") or "").strip().upper()


def _cell(row: Mapping[str, object]) -> tuple[str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
    )


def _has_model_value(row: Mapping[str, object]) -> bool:
    return any(
        not is_nullish(row.get(key))
        for key in ("normalized_value", "capex_usd")
    )


def _has_any_value(row: Mapping[str, object]) -> bool:
    return _has_model_value(row) or not is_nullish(row.get("raw_value"))


def _existing_e_row(audit_rows: list[dict[str, str]], entity: str, parameter: str) -> bool:
    for row in audit_rows:
        if _cell(row) != (entity, parameter):
            continue
        if _tag(row) != ESTIMATE_QUALITY_TAG:
            continue
        if str(row.get("held_estimate_status") or "").strip().lower() == "reject":
            continue
        if str(row.get("relevance_status") or "").strip().lower() == "reject":
            continue
        return True
    return False


def _selected_real_row(
    audit_rows: list[dict[str, str]],
    entity: str,
    parameter: str,
) -> bool:
    for row in audit_rows:
        if _cell(row) != (entity, parameter):
            continue
        if is_pinned_row(row):
            return True
        if _tag(row) == ESTIMATE_QUALITY_TAG:
            continue
        if _truthy(row.get("selected_for_model")) and _has_model_value(row):
            return True
    return False


def _main_input_index(main_rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {
        _cell(row): row
        for row in main_rows
        if row.get("entity") or row.get("parameter")
    }


def _cell_is_blank(
    *,
    schema: Schema,
    entity: str,
    parameter: str,
    audit_rows: list[dict[str, str]],
    main_by_cell: Mapping[tuple[str, str], Mapping[str, str]],
    force_refresh: bool,
) -> bool:
    del schema
    main = main_by_cell.get((entity, parameter))
    if main:
        if is_pinned_row(main):
            return False
        if _has_model_value(main):
            if _tag(main) == ESTIMATE_QUALITY_TAG:
                return force_refresh
            return False

    if _selected_real_row(audit_rows, entity, parameter):
        return False
    if _existing_e_row(audit_rows, entity, parameter) and not force_refresh:
        return False
    return True


def _parameter_entry(schema: Schema, parameter_id: str) -> dict[str, object]:
    parameter = schema.parameter(parameter_id)
    keys = (
        "id",
        "label",
        "rule_type",
        "units",
        "numerator_units",
        "per",
        "canonical_unit",
        "basis",
        "market_basis",
        "capex_form",
        "first_class",
        "context_free",
        "reference_value",
        "scope",
        "description",
    )
    return {key: parameter[key] for key in keys if key in parameter}


def _entity_entry(schema: Schema, entity_id: str) -> dict[str, object]:
    if entity_id == GLOBAL_ENTITY_ID:
        return {
            "entity": GLOBAL_ENTITY_ID,
            "entity_name": "Reference values",
            "entity_description": "Global context-free reference-value parameters.",
            "scope_frame": {
                "in_scope": "Reference values declared in the schema for the whole TEA.",
                "known_out_of_scope": [],
            },
            "estimation_policy": "first_principles_only",
        }
    entity = schema.entity(entity_id)
    return {
        "entity": entity_id,
        "entity_name": entity.get("name", ""),
        "entity_description": entity.get("description", ""),
        "entity_output": entity.get("output", ""),
        "scope_frame": entity.get("scope_frame", {}),
        "estimation_policy": entity.get("estimation_policy", "first_principles_only"),
    }


def collect_existing_real_extractions(
    audit_rows: list[dict[str, str]],
    schema: Schema,
    entity_id: str,
) -> list[dict[str, object]]:
    """Return A/B/C-style rows for the entity as anti-hallucination anchors."""

    anchors: list[dict[str, object]] = []
    for row in audit_rows:
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        tag = _tag(row)
        if not tag or tag in ANCHOR_EXCLUDED_TAGS:
            continue
        parameter_id = str(row.get("parameter") or "").strip()
        if not schema.has_parameter(parameter_id) or not _has_any_value(row):
            continue
        anchor = {
            "parameter": parameter_id,
            "parameter_label": schema.parameter(parameter_id).get("label", parameter_id),
            "quality_tag": tag,
            "source_key": row.get("source_key", ""),
            "source_url": row.get("source_url", ""),
            "page_ref": row.get("page_ref", ""),
            "raw_value": row.get("raw_value", ""),
            "raw_units": row.get("raw_units", ""),
            "normalized_value": row.get("normalized_value", ""),
            "normalized_units": row.get("normalized_units", ""),
            "capex_usd": row.get("capex_usd", ""),
            "capex_form": row.get("capex_form", ""),
        }
        anchors.append({key: value for key, value in anchor.items() if value not in ("", None)})
    return anchors


def build_manifest(
    *,
    schema_path: str | Path,
    audit_path: str | Path = "Audit_normalized_consolidated.csv",
    main_input_path: str | Path | None = "Main Input.csv",
    force_refresh: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
    main_rows = (
        read_rows(main_input_path, required_columns=MAIN_INPUT_FIELDNAMES, missing_ok=True)
        if main_input_path is not None
        else []
    )
    main_by_cell = _main_input_index(main_rows)

    blanks_by_entity: dict[str, list[dict[str, object]]] = {}
    for entity_id, parameter_id in schema.skeleton_cells():
        if not _cell_is_blank(
            schema=schema,
            entity=entity_id,
            parameter=parameter_id,
            audit_rows=audit_rows,
            main_by_cell=main_by_cell,
            force_refresh=force_refresh,
        ):
            continue
        blanks_by_entity.setdefault(entity_id, []).append(_parameter_entry(schema, parameter_id))

    entity_order = list(schema.entity_ids)
    if GLOBAL_ENTITY_ID in blanks_by_entity:
        entity_order.append(GLOBAL_ENTITY_ID)

    entities: list[dict[str, object]] = []
    for entity_id in entity_order:
        blank_parameters = blanks_by_entity.get(entity_id, [])
        if not blank_parameters:
            continue
        entry = _entity_entry(schema, entity_id)
        entry["blank_parameters"] = blank_parameters
        entry["existing_real_extractions"] = collect_existing_real_extractions(
            audit_rows,
            schema,
            entity_id,
        )
        entities.append(entry)

    return {
        "generated_at_iso": _now_iso(),
        "schema_tea_id": schema.tea_id,
        "display_name": schema.display_name,
        "force_refresh": force_refresh,
        "functional_unit": schema.functional_unit,
        "basis": schema.basis,
        "quality_tags": schema.quality_tags,
        "comparable_rubric": schema.comparable_rubric or {"dimensions": [], "hard_rule": ""},
        "entities": entities,
        "counts": {
            "entities": len(entities),
            "blank_cells": sum(len(entry["blank_parameters"]) for entry in entities),
        },
    }


def write_manifest(path: str | Path, manifest: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("Audit_normalized_consolidated.csv"),
        help="Consolidated Audit CSV; missing is treated as no prior rows",
    )
    parser.add_argument(
        "--main-input",
        type=Path,
        default=Path("Main Input.csv"),
        help="Current Main Input CSV; missing is treated as no selected rows",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("estimation_manifest.json"),
        help="Manifest JSON to write",
    )
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")
    args = parser.parse_args(argv)

    try:
        manifest = build_manifest(
            schema_path=args.schema,
            audit_path=args.audit,
            main_input_path=args.main_input,
            force_refresh=args.force_refresh,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.dry_run:
        write_manifest(args.output, manifest)

    prefix = "[dry-run] " if args.dry_run else ""
    counts = manifest["counts"]
    print(
        f"{prefix}{counts['blank_cells']} blank cell(s) across "
        f"{counts['entities']} entit(y/ies) -> {args.output}"
    )
    for entity in manifest["entities"]:
        params = ", ".join(p["id"] for p in entity["blank_parameters"])
        print(f"  {entity['entity']}: {len(entity['blank_parameters'])} blank(s) - {params}")
    if not manifest["entities"]:
        print("No estimation work to do.")
    else:
        print("Next: invoke prompts/estimation-orchestrator.md with this manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
