"""Append Phase 6 estimate rows and register their cited sources.

Consumes the orchestrator/populator JSON payload, validates estimate rows
against ``tea-schema.json``, writes E-quality Audit rows, and registers cited
sources in ``Sources.csv`` with ``source_role=estimate`` (or upgrades an
existing extraction source to ``both``).

Examples:
    python scripts/append_estimation_rows.py --schema tea-schema.json --input estimation_output.json
    python scripts/append_estimation_rows.py --schema tea-schema.json --input estimation_output.json --force-refresh
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping

from lib.csvio import (
    AUDIT_FIELDNAMES,
    SOURCES_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from lib.extraction import is_nullish
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema
from lib.search import SOURCE_KEY_RE, is_open_access_notes
from lib.source_url import SourceUrlError, source_url_for


# Backed single-anchor estimates keep the E tag; unbacked (Loop 3) estimates get
# their own loud U tag so they are impossible to miss in the inputs and summary.
BACKED_TAG = "E"
UNBACKED_TAG = "U"
ESTIMATE_TAGS = {BACKED_TAG, UNBACKED_TAG}
# Kept for callers that import the old name (now means "the backed estimate tag").
ESTIMATE_QUALITY_TAG = BACKED_TAG

#: An estimate is either built on one real, extracted anchor (single_anchor) or,
#: when no anchor can be sourced, an explicitly-flagged transparent estimate
#: (unbacked). The old comparable/first_principles/failed split is retired — the
#: Loop 1->2->3 ladder is the control flow now.
ALLOWED_METHODS = {"single_anchor", "unbacked"}
METHOD_TAG = {"single_anchor": BACKED_TAG, "unbacked": UNBACKED_TAG}
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

AUDIT_PROJECTABLE_KEYS = (
    "entity",
    "parameter",
    "source_key",
    "source_url",
    "page_ref",
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "quality_tag",
    "normalized_value",
    "normalized_units",
    "transform_steps",
    "capex_usd",
    "capex_form",
    "capex_basis_year",
    "capex_basis_scale",
    "capex_basis_scale_units",
    "capex_notes",
    "review_value",
    "review_units",
    "review_steps",
    "extractor_notes",
    "relevance_status",
    "input_origin",
    "notes",
)

NUMERIC_OUTPUTS = (
    "normalized_value",
    "capex_usd",
    "review_value",
)


class EstimationValidationError(ValueError):
    """Raised when an estimation payload fails mechanical validation."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise EstimationValidationError([f"{path}: top-level JSON must be an object"])
    return doc


def _cell(row: Mapping[str, object]) -> tuple[str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
    )


def _method(justification: Mapping[str, object]) -> str:
    return str(justification.get("method") or "").strip()


def _float(value: object) -> float | None:
    if is_nullish(value):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _as_object(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _source_key(raw: Mapping[str, object]) -> str:
    return str(raw.get("source_key") or raw.get("key") or "").strip()


def _source_url(raw: Mapping[str, object]) -> str:
    return str(raw.get("source_url") or raw.get("url") or "").strip()


def normalize_cited_source(raw: Mapping[str, object], *, access_date: str) -> dict[str, str]:
    key = _source_key(raw)
    url = _source_url(raw)
    row = blank_row(SOURCES_FIELDNAMES)
    access_notes = str(raw.get("access_notes") or "").strip()
    notes = str(raw.get("notes") or "registered_from=estimation")
    if access_notes:
        notes = f"{notes}; access_notes={access_notes}"
    row.update(
        {
            "source_key": key,
            "authors": str(raw.get("authors") or ""),
            "title": str(raw.get("title") or ""),
            "year": str(raw.get("year") or ""),
            "publisher_or_journal": str(raw.get("publisher_or_journal") or ""),
            "source_url": url,
            "doi": str(raw.get("doi") or ""),
            "access_date": str(raw.get("access_date") or access_date),
            "page_or_table_reference": str(
                raw.get("page_or_table_reference") or raw.get("page_ref") or ""
            ),
            "source_role": "estimate",
            "notes": notes,
        }
    )
    return row


def cited_sources_for_row(row: Mapping[str, object]) -> list[dict[str, str]]:
    """Return structured cited source rows carried by an estimate row.

    A single-anchor estimate cites exactly the one extracted anchor source; the
    anchor object itself counts as a cited source so it is registered.
    """

    justification = _as_object(row.get("estimate_justification"))
    raw_sources: list[object] = []
    raw_sources.extend(_as_list(row.get("cited_sources")))
    raw_sources.extend(_as_list(justification.get("cited_sources")))

    anchor = justification.get("anchor")
    if isinstance(anchor, Mapping) and _source_key(anchor):
        raw_sources.append(anchor)

    access_date = dt.date.today().isoformat()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_sources:
        if not isinstance(item, Mapping):
            continue
        source = normalize_cited_source(item, access_date=access_date)
        key = source["source_key"]
        if key and key not in seen:
            out.append(source)
            seen.add(key)
    return out


def _merge_role(existing: str, incoming: str = "estimate") -> str:
    role = (existing or "").strip().lower()
    if role == "both" or (role == "extraction" and incoming == "estimate"):
        return "both"
    if role == "estimate" or (role == "" and incoming == "estimate"):
        return "estimate"
    if role == "extraction":
        return "both"
    if incoming == "estimate":
        return "estimate"
    return incoming


def register_estimate_sources(
    *,
    sources_path: str | Path,
    cited_sources: list[dict[str, str]],
    dry_run: bool = False,
) -> dict[str, object]:
    existing_rows = read_rows(sources_path, required_columns=SOURCES_FIELDNAMES, missing_ok=True)
    by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing_rows:
        key = (row.get("source_key") or "").strip()
        if not key:
            continue
        if key not in by_key:
            by_key[key] = {name: row.get(name, "") for name in SOURCES_FIELDNAMES}
            order.append(key)

    appended: list[str] = []
    updated: list[str] = []
    errors: list[str] = []
    for source in cited_sources:
        key = source["source_key"]
        url = source["source_url"]
        if not key:
            errors.append("cited source missing source_key")
            continue
        if not SOURCE_KEY_RE.match(key):
            errors.append(f"cited source_key {key!r} must be kebab-case and <=64 chars")
        if not url or not HTTP_URL_RE.match(url):
            errors.append(f"cited source {key!r} must provide an HTTP(S) source_url")
        if key in by_key:
            existing = by_key[key]
            existing_url = (existing.get("source_url") or "").strip()
            if existing_url and url and existing_url != url:
                errors.append(
                    f"Sources.csv has source_url {existing_url!r} for {key!r}, "
                    f"but estimate cites {url!r}"
                )
                continue
            for field in SOURCES_FIELDNAMES:
                if not (existing.get(field) or "").strip() and (source.get(field) or "").strip():
                    existing[field] = source[field]
            new_role = _merge_role(existing.get("source_role", ""), "estimate")
            if existing.get("source_role") != new_role:
                existing["source_role"] = new_role
                updated.append(key)
            elif key not in updated:
                updated.append(key)
        else:
            by_key[key] = source
            order.append(key)
            appended.append(key)

    if errors:
        raise EstimationValidationError(errors)

    if not dry_run:
        write_rows(sources_path, SOURCES_FIELDNAMES, [by_key[key] for key in order])

    return {"appended": appended, "updated": updated, "sources_path": Path(sources_path)}


def _validate_cited_sources(
    *,
    row: Mapping[str, object],
    schema: Schema,
    method: str,
    where: str,
    errors: list[str],
) -> list[dict[str, str]]:
    sources = cited_sources_for_row(row)
    if method != "single_anchor":
        # Unbacked estimates carry no anchor source; nothing to register.
        return sources
    if not sources:
        errors.append(f"{where}: single_anchor estimates must include the extracted anchor source")
        return sources

    keys = {source["source_key"] for source in sources if source["source_key"]}
    for source in sources:
        key = source["source_key"]
        url = source["source_url"]
        if not key:
            errors.append(f"{where}: cited source missing source_key")
        elif not SOURCE_KEY_RE.match(key):
            errors.append(f"{where}: cited source_key {key!r} must be kebab-case and <=64 chars")
        if not url or not HTTP_URL_RE.match(url):
            errors.append(f"{where}: cited source {key or '<blank>'!r} must include HTTP(S) source_url")
        if schema.is_auto and not is_open_access_notes(source.get("notes")):
            errors.append(
                f"{where}: Auto mode cited source {key or '<blank>'!r} must include "
                "access_notes explicitly confirming open/public full-text access"
            )

    row_source_key = str(row.get("source_key") or "").strip()
    if True:
        if not row_source_key:
            errors.append(f"{where}: source_key is required on single_anchor estimate rows")
        elif row_source_key not in keys:
            errors.append(
                f"{where}: row source_key {row_source_key!r} must be one of the cited source keys"
            )
        else:
            cited_url = next(
                (source["source_url"] for source in sources if source["source_key"] == row_source_key),
                "",
            )
            supplied_url = str(row.get("source_url") or "").strip()
            if supplied_url and supplied_url != cited_url:
                errors.append(
                    f"{where}: row source_url {supplied_url!r} does not match cited source "
                    f"{row_source_key!r} URL {cited_url!r}"
                )
    return sources


def _has_value(row: Mapping[str, object]) -> bool:
    return any(
        not is_nullish(row.get(key))
        for key in ("raw_value", "normalized_value", "capex_usd")
    )


def _validate_method_shape(
    *,
    row: Mapping[str, object],
    schema: Schema,
    method: str,
    where: str,
    errors: list[str],
) -> None:
    del schema
    j = _as_object(row.get("estimate_justification"))

    # Common contract: every estimate names the bridging assumption, the equation
    # it applies, the derivation, and which loop of the ladder produced it. Every
    # estimate also carries a numeric value (no blank "failed" rows any more).
    if not str(j.get("enabling_assumption") or "").strip():
        errors.append(f"{where}: estimate_justification.enabling_assumption is required")
    if not str(j.get("equation") or "").strip():
        errors.append(f"{where}: estimate_justification.equation is required")
    if not _as_list(j.get("derivation_steps")):
        errors.append(f"{where}: estimate_justification.derivation_steps must be a non-empty list")
    loop = j.get("loop")
    if loop not in (1, 2, 3):
        errors.append(f"{where}: estimate_justification.loop must be 1, 2, or 3")
    if not _has_value(row):
        errors.append(f"{where}: every estimate must carry a numeric value (no blank cells)")

    if method == "single_anchor":
        if loop == 3:
            errors.append(f"{where}: loop 3 has no sourceable anchor; use method 'unbacked'")
        anchor = j.get("anchor")
        if not isinstance(anchor, Mapping):
            errors.append(f"{where}: single_anchor method requires estimate_justification.anchor")
        else:
            if not str(anchor.get("source_key") or "").strip():
                errors.append(f"{where}: anchor.source_key is required")
            if is_nullish(anchor.get("value")):
                errors.append(f"{where}: anchor.value is required")
            if not str(anchor.get("page_ref") or "").strip():
                errors.append(f"{where}: anchor.page_ref is required (real extraction provenance)")
            atag = str(anchor.get("quality_tag") or "").strip().upper()
            if not atag or atag in ESTIMATE_TAGS:
                errors.append(
                    f"{where}: anchor.quality_tag must be a real extraction tag (A-D), "
                    "not blank or an estimate tag"
                )
        for idx, c in enumerate(_as_list(j.get("assumed_constants"))):
            if not isinstance(c, Mapping) or not str(c.get("symbol") or "").strip() or is_nullish(c.get("value")):
                errors.append(f"{where}: assumed_constants[{idx}] needs a symbol and a value")
    elif method == "unbacked":
        if loop != 3:
            errors.append(f"{where}: unbacked estimates are loop 3 (no sourceable anchor)")
        anchor = j.get("anchor")
        if isinstance(anchor, Mapping) and _source_key(anchor):
            errors.append(f"{where}: unbacked estimate must not carry an anchor source")
        if j.get("unbacked") is not True:
            errors.append(f"{where}: unbacked estimate must set estimate_justification.unbacked = true")


def _validate_numeric_bounds(
    *,
    row: Mapping[str, object],
    schema: Schema,
    parameter_id: str,
    method: str,
    where: str,
    errors: list[str],
) -> None:
    if method == "failed":
        return
    rule_type = schema.rule_type(parameter_id)
    normalized = _float(row.get("normalized_value"))
    capex = _float(row.get("capex_usd"))
    if rule_type == "FRACTION" and normalized is not None and not (0 <= normalized <= 1):
        errors.append(f"{where}: FRACTION normalized_value {normalized:g} must be in [0, 1]")
    if rule_type in {"MONETARY", "INTENSITY", "RATE"} and normalized is not None and normalized < 0:
        errors.append(f"{where}: {rule_type} normalized_value {normalized:g} must be >= 0")
    if rule_type == "CAPEX" and capex is not None and capex <= 0:
        errors.append(f"{where}: CAPEX capex_usd {capex:g} must be > 0")


def validate_estimation_payload(doc: Mapping[str, object], schema: Schema) -> list[dict[str, str]]:
    errors: list[str] = []
    if "rows" not in doc or not isinstance(doc.get("rows"), list):
        raise EstimationValidationError(["rows: missing top-level list"])
    if "force_refresh" in doc and not isinstance(doc.get("force_refresh"), bool):
        errors.append("force_refresh must be a boolean")
    tea_id = str(doc.get("schema_tea_id") or "").strip()
    if tea_id and tea_id != schema.tea_id:
        errors.append(f"schema_tea_id {tea_id!r} does not match {schema.tea_id!r}")

    cited_sources: list[dict[str, str]] = []
    seen_rows: set[tuple[str, str]] = set()
    for idx, row in enumerate(doc.get("rows") or [], start=0):
        where = f"rows[{idx}]"
        if not isinstance(row, Mapping):
            errors.append(f"{where}: must be an object")
            continue
        entity, parameter = _cell(row)
        if not entity:
            errors.append(f"{where}: entity is required")
        elif entity != GLOBAL_ENTITY_ID and not schema.has_entity(entity):
            errors.append(f"{where}: unknown entity {entity!r}")
        if not parameter:
            errors.append(f"{where}: parameter is required")
        elif not schema.has_parameter(parameter):
            errors.append(f"{where}: unknown parameter {parameter!r}")
        if entity and parameter and schema.has_parameter(parameter):
            if entity == GLOBAL_ENTITY_ID or schema.has_entity(entity):
                if not schema.applies(parameter, entity):
                    errors.append(
                        f"{where}: parameter {parameter!r} does not apply to entity {entity!r}"
                    )
        if (entity, parameter) in seen_rows:
            errors.append(f"{where}: duplicate estimate row for ({entity},{parameter})")
        seen_rows.add((entity, parameter))

        justification = _as_object(row.get("estimate_justification"))
        if not justification:
            errors.append(f"{where}: estimate_justification must be an object")
            continue
        method = _method(justification)
        if method not in ALLOWED_METHODS:
            errors.append(f"{where}: method {method!r} must be one of {sorted(ALLOWED_METHODS)}")
            continue

        # E for a backed single-anchor estimate, U for an unbacked (loop 3) one.
        tag = str(row.get("quality_tag") or METHOD_TAG[method]).strip().upper()
        if tag != METHOD_TAG[method]:
            errors.append(
                f"{where}: quality_tag must be {METHOD_TAG[method]!r} for method {method!r}"
            )

        cited_sources.extend(
            _validate_cited_sources(
                row=row,
                schema=schema,
                method=method,
                where=where,
                errors=errors,
            )
        )
        _validate_method_shape(row=row, schema=schema, method=method, where=where, errors=errors)
        if schema.has_parameter(parameter):
            _validate_numeric_bounds(
                row=row,
                schema=schema,
                parameter_id=parameter,
                method=method,
                where=where,
                errors=errors,
            )

    if errors:
        raise EstimationValidationError(errors)
    return cited_sources


def _existing_e_cells(audit_rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {
        _cell(row)
        for row in audit_rows
        if str(row.get("quality_tag") or "").strip().upper() in ESTIMATE_TAGS
    }


def project_estimate_row(
    row: Mapping[str, object],
    *,
    sources_path: str | Path,
    source_url_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    out = blank_row(AUDIT_FIELDNAMES)
    for key in AUDIT_PROJECTABLE_KEYS:
        value = row.get(key, "")
        out[key] = "" if value is None else str(value)
    method = _method(_as_object(row.get("estimate_justification")))
    out["quality_tag"] = str(row.get("quality_tag") or METHOD_TAG.get(method, BACKED_TAG)).strip().upper()
    out["relevance_status"] = str(row.get("relevance_status") or "clear")
    out["input_origin"] = str(row.get("input_origin") or "estimated")
    out["held_estimate_status"] = ""
    out["held_estimate_answer"] = ""
    justification = _as_object(row.get("estimate_justification"))
    out["estimate_justification"] = json.dumps(
        justification,
        ensure_ascii=False,
        sort_keys=True,
    )
    if out["source_key"]:
        overrides = source_url_overrides or {}
        out["source_url"] = overrides.get(out["source_key"]) or source_url_for(
            out["source_key"],
            sources_path,
            required=True,
        )
    return out


def append_estimation_rows(
    *,
    schema_path: str | Path,
    input_path: str | Path = "estimation_output.json",
    audit_path: str | Path = "Audit.csv",
    sources_path: str | Path = "Sources.csv",
    force_refresh: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    schema = load_schema(schema_path)
    doc = load_json(input_path)
    payload_force = bool(doc.get("force_refresh", False))
    if payload_force != force_refresh:
        raise EstimationValidationError(
            [
                "payload force_refresh="
                f"{payload_force} but CLI --force-refresh={force_refresh}; they must agree"
            ]
        )

    cited_sources = validate_estimation_payload(doc, schema)
    audit_rows = read_rows(audit_path, required_columns=AUDIT_FIELDNAMES, missing_ok=True)
    incoming_rows = [row for row in doc.get("rows", []) if isinstance(row, Mapping)]
    incoming_cells = {_cell(row) for row in incoming_rows}
    existing_e_cells = _existing_e_cells(audit_rows)

    rows_to_append: list[Mapping[str, object]] = []
    skipped_existing_e: list[tuple[str, str]] = []
    for row in incoming_rows:
        cell = _cell(row)
        if cell in existing_e_cells and not force_refresh:
            skipped_existing_e.append(cell)
            continue
        rows_to_append.append(row)

    if force_refresh and incoming_cells:
        kept_audit_rows = [
            row
            for row in audit_rows
            if not (
                _cell(row) in incoming_cells
                and str(row.get("quality_tag") or "").strip().upper() in ESTIMATE_TAGS
            )
        ]
    else:
        kept_audit_rows = list(audit_rows)
    dropped = len(audit_rows) - len(kept_audit_rows)

    registered = register_estimate_sources(
        sources_path=sources_path,
        cited_sources=cited_sources,
        dry_run=dry_run,
    )
    source_url_overrides = {
        source["source_key"]: source["source_url"]
        for source in cited_sources
        if source.get("source_key") and source.get("source_url")
    }
    projected = [
        project_estimate_row(
            row,
            sources_path=sources_path,
            source_url_overrides=source_url_overrides,
        )
        for row in rows_to_append
    ]
    final_rows = kept_audit_rows + projected
    if not dry_run:
        write_rows(audit_path, AUDIT_FIELDNAMES, final_rows)

    return {
        "rows_appended": projected,
        "skipped_existing_e": skipped_existing_e,
        "dropped_existing_e": dropped,
        "registered_sources": registered,
        "audit_path": Path(audit_path),
        "sources_path": Path(sources_path),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True, help="Path to tea-schema.json")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("estimation_output.json"),
        help="Orchestrator estimation output JSON",
    )
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit CSV to update")
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"), help="Sources CSV to update")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")
    args = parser.parse_args(argv)

    try:
        result = append_estimation_rows(
            schema_path=args.schema,
            input_path=args.input,
            audit_path=args.audit,
            sources_path=args.sources,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
        )
    except (OSError, json.JSONDecodeError, ValueError, SourceUrlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    registered = result["registered_sources"]
    print(
        f"{prefix}{len(result['rows_appended'])} estimate row(s) appended; "
        f"{len(result['skipped_existing_e'])} skipped; "
        f"{result['dropped_existing_e']} prior E row(s) dropped."
    )
    print(
        f"{prefix}Sources: {len(registered['appended'])} estimate source(s) appended, "
        f"{len(registered['updated'])} existing source(s) updated."
    )
    if result["rows_appended"]:
        print("Next: run sweep_held_estimates.py before normalizing E rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
