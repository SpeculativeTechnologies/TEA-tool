"""Shared helpers for the schema-driven extraction lane.

T4 keeps the extraction step deliberately mechanical: extractor JSON is checked
against ``tea-schema.json``, converted into the stable ``Audit.csv`` contract,
and withheld ``hold`` rows are surfaced for analyst review before downstream
normalization can proceed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .csvio import AUDIT_FIELDNAMES, blank_row, read_rows
from .schema import GLOBAL_ENTITY_ID, Schema
from .source_url import SourceUrlError, load_source_urls


ALLOWED_RELEVANCE = {"clear", "hold", "reject", "pinned"}
EXTRACTOR_RELEVANCE = {"clear", "hold", "reject"}
NULLISH_STRINGS = {"", "null", "none", "n/a"}

RAW_FIELDS = (
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
)

NULLED_ON_REJECT = (
    "page_ref",
    "raw_value",
    "raw_units",
    "raw_basis_scale",
    "raw_basis_scale_units",
    "raw_basis_year",
    "quality_tag",
)


class ExtractionValidationError(ValueError):
    """Raised when extractor output cannot be safely appended to Audit.csv."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


class ExtractionHoldError(RuntimeError):
    """Raised by downstream phases when unresolved extraction holds remain."""

    def __init__(self, hold_rows: list[dict[str, str]]):
        self.hold_rows = hold_rows
        preview = ", ".join(
            f"{row.get('entity')}:{row.get('parameter')}@{row.get('source_key')}"
            for row in hold_rows[:5]
        )
        suffix = f" ({preview})" if preview else ""
        super().__init__(
            f"{len(hold_rows)} unresolved extraction hold row(s) remain{suffix}; "
            "run sweep_held_questions.py and apply_held_verdicts.py before continuing."
        )


@dataclass(frozen=True)
class IngestResult:
    """Rows and counts produced from one extractor output document."""

    audit_rows: list[dict[str, str]]
    counts: dict[str, int]


def is_nullish(value: object) -> bool:
    """Return True for JSON/CSV null spellings used by extractor outputs."""

    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in NULLISH_STRINGS
    return False


def cell_key(entity: object, parameter: object) -> tuple[str, str]:
    return (str(entity or "").strip(), str(parameter or "").strip())


def audit_hold_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    """Stable key for matching a held queue row back to an Audit.csv row."""

    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
        str(row.get("page_ref") or "").strip(),
        str(row.get("raw_value") or "").strip(),
    )


def allowed_extraction_quality_tags(schema: Schema) -> set[str]:
    """Quality tags valid for extraction rows.

    ``E`` is reserved for estimates. If a custom config omits all non-E tags,
    fall back to the declared set so the validator remains config-driven.
    """

    tags = set(schema.quality_tags)
    non_estimate = tags - {"E"}
    return non_estimate or tags


def _string_or_blank(value: object) -> str:
    return "" if is_nullish(value) else str(value)


def _status(row: Mapping[str, object]) -> str:
    return str(row.get("relevance_status") or "clear").strip().lower()


def _row_source_key(row: Mapping[str, object], top_source_key: str) -> str:
    return str(row.get("source_key") or top_source_key or "").strip()


def _row_source_url(row: Mapping[str, object], top_source_url: str) -> str:
    return str(row.get("source_url") or top_source_url or "").strip()


def validate_top_level(doc: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ("source_key", "extracted_rows"):
        if key not in doc:
            errors.append(f"top-level key {key!r} missing")
    if "extracted_rows" in doc and not isinstance(doc.get("extracted_rows"), list):
        errors.append("extracted_rows must be a list")
    if "extraction_summary" in doc and not isinstance(doc.get("extraction_summary"), Mapping):
        errors.append("extraction_summary must be an object when present")
    return errors


def validate_extracted_row(
    row: Mapping[str, object],
    *,
    idx: int,
    schema: Schema,
    top_source_key: str,
    source_quality_fallback: str = "",
) -> list[str]:
    """Return validation errors for one extractor row."""

    errors: list[str] = []
    where = f"row {idx}"
    entity, parameter = cell_key(row.get("entity"), row.get("parameter"))

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

    source_key = _row_source_key(row, top_source_key)
    if not source_key:
        errors.append(f"{where}: source_key is required")
    elif top_source_key and source_key != top_source_key:
        errors.append(f"{where}: source_key {source_key!r} != top-level {top_source_key!r}")

    status = _status(row)
    if status not in EXTRACTOR_RELEVANCE:
        errors.append(
            f"{where}: relevance_status {row.get('relevance_status')!r} must be one of "
            f"{sorted(EXTRACTOR_RELEVANCE)}"
        )

    raw_value = row.get("raw_value")
    has_value = not is_nullish(raw_value)
    if has_value and not isinstance(raw_value, str):
        errors.append(f"{where}: raw_value must be a string or null")

    page_ref = row.get("page_ref")
    raw_units = row.get("raw_units")
    quality_tag = row.get("quality_tag")
    analyst_question = row.get("analyst_question")
    notes = row.get("extractor_notes")

    allowed_quality = allowed_extraction_quality_tags(schema)
    if has_value:
        if is_nullish(page_ref):
            errors.append(f"{where}: page_ref is required when raw_value is present")
        rule_type = schema.rule_type(parameter) if schema.has_parameter(parameter) else ""
        if rule_type not in {"TEXT", "JSON"} and is_nullish(raw_units):
            errors.append(f"{where}: raw_units is required when raw_value is present")
        if is_nullish(quality_tag):
            if source_quality_fallback not in allowed_quality:
                errors.append(
                    f"{where}: quality_tag is required on value-bearing rows "
                    "(or pass a valid source-quality fallback)"
                )
        elif str(quality_tag).strip() not in allowed_quality:
            errors.append(
                f"{where}: quality_tag {quality_tag!r} is not one of "
                f"{sorted(allowed_quality)}"
            )
    else:
        for key in ("page_ref", "raw_units", "raw_basis_scale", "raw_basis_scale_units",
                    "raw_basis_year", "quality_tag"):
            if not is_nullish(row.get(key)):
                errors.append(
                    f"{where}: raw_value is null but {key} is populated "
                    "(blank not-found/reject rows before ingest)"
                )
        if is_nullish(notes):
            errors.append(f"{where}: extractor_notes is required when raw_value is null")

    if status == "hold":
        if not has_value:
            errors.append(f"{where}: hold rows must capture the candidate raw_value")
        if is_nullish(analyst_question):
            errors.append(f"{where}: hold rows require a self-contained analyst_question")
    elif status == "reject":
        if has_value:
            errors.append(f"{where}: reject rows must blank raw_value")
        if not is_nullish(analyst_question):
            errors.append(f"{where}: reject rows must not carry analyst_question")
        if is_nullish(notes):
            errors.append(f"{where}: reject rows require extractor_notes naming the out-of-scope basis")
    elif status == "clear":
        if not is_nullish(analyst_question):
            errors.append(f"{where}: analyst_question belongs only on hold rows")

    return errors


def validate_extractor_doc(
    doc: Mapping[str, object],
    schema: Schema,
    *,
    source_quality_fallback: str = "",
    expected_targets: Iterable[tuple[str, str]] | None = None,
) -> None:
    """Validate one extractor JSON document, raising on any issue."""

    errors = validate_top_level(doc)
    if errors:
        raise ExtractionValidationError(errors)

    top_source_key = str(doc.get("source_key") or "").strip()
    rows = doc.get("extracted_rows") or []
    row_cells: set[tuple[str, str]] = set()
    for idx, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            errors.append(f"row {idx}: must be an object")
            continue
        row_cells.add(cell_key(raw_row.get("entity"), raw_row.get("parameter")))
        errors.extend(
            validate_extracted_row(
                raw_row,
                idx=idx,
                schema=schema,
                top_source_key=top_source_key,
                source_quality_fallback=source_quality_fallback,
            )
        )

    if expected_targets is not None:
        expected = {cell_key(entity, parameter) for entity, parameter in expected_targets}
        missing = sorted(expected - row_cells)
        if missing:
            errors.append(f"missing extracted row(s) for expected target(s): {missing!r}")

    if errors:
        raise ExtractionValidationError(errors)


def _source_url_resolver(sources_path: str | Path) -> dict[str, str]:
    return load_source_urls(sources_path)


def source_url_from_map(source_key: str, source_urls: Mapping[str, str]) -> str:
    key = (source_key or "").strip()
    if not key:
        raise SourceUrlError("source_key is required to resolve source_url")
    url = (source_urls.get(key) or "").strip()
    if not url:
        raise SourceUrlError(f"no source_url found for source_key {key!r}")
    return url


def json_row_to_audit_row(
    row: Mapping[str, object],
    *,
    top_source_key: str,
    top_source_url: str,
    source_urls: Mapping[str, str],
    source_quality_fallback: str = "",
) -> dict[str, str]:
    """Project one validated extractor row into the Audit.csv schema."""

    out = blank_row(AUDIT_FIELDNAMES)
    for key in (
        "entity",
        "parameter",
        "page_ref",
        "raw_value",
        "raw_units",
        "raw_basis_scale",
        "raw_basis_scale_units",
        "raw_basis_year",
        "quality_tag",
        "extractor_notes",
        "analyst_question",
        "notes",
    ):
        out[key] = _string_or_blank(row.get(key))

    source_key = _row_source_key(row, top_source_key)
    out["source_key"] = source_key
    resolved_url = source_url_from_map(source_key, source_urls)
    supplied_url = _row_source_url(row, top_source_url)
    if supplied_url and supplied_url != resolved_url:
        raise SourceUrlError(
            f"extractor source_url {supplied_url!r} does not match Sources.csv "
            f"for source_key {source_key!r}: {resolved_url!r}"
        )
    out["source_url"] = resolved_url
    out["relevance_status"] = _status(row)

    if out["raw_value"] and not out["quality_tag"] and source_quality_fallback:
        out["quality_tag"] = source_quality_fallback
    return out


def extractor_doc_to_audit_rows(
    doc: Mapping[str, object],
    schema: Schema,
    *,
    sources_path: str | Path,
    source_quality_fallback: str = "",
    expected_targets: Iterable[tuple[str, str]] | None = None,
) -> IngestResult:
    """Validate and convert an extractor JSON object into Audit.csv rows."""

    validate_extractor_doc(
        doc,
        schema,
        source_quality_fallback=source_quality_fallback,
        expected_targets=expected_targets,
    )
    source_urls = _source_url_resolver(sources_path)
    top_source_key = str(doc.get("source_key") or "").strip()
    top_source_url = str(doc.get("source_url") or "").strip()
    resolved_top_url = source_url_from_map(top_source_key, source_urls)
    if top_source_url and top_source_url != resolved_top_url:
        raise SourceUrlError(
            f"extractor source_url {top_source_url!r} does not match Sources.csv "
            f"for source_key {top_source_key!r}: {resolved_top_url!r}"
        )
    audit_rows = [
        json_row_to_audit_row(
            row,
            top_source_key=top_source_key,
            top_source_url=top_source_url,
            source_urls=source_urls,
            source_quality_fallback=source_quality_fallback,
        )
        for row in doc.get("extracted_rows", [])
    ]
    return IngestResult(audit_rows=audit_rows, counts=categorize_rows(audit_rows))


def categorize_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = {
        "rows": 0,
        "with_values": 0,
        "not_found": 0,
        "clear": 0,
        "hold": 0,
        "reject": 0,
        "pinned": 0,
    }
    for row in rows:
        counts["rows"] += 1
        if is_nullish(row.get("raw_value")):
            counts["not_found"] += 1
        else:
            counts["with_values"] += 1
        status = _status(row)
        if status in counts:
            counts[status] += 1
    return counts


def unresolved_hold_rows(audit_path: str | Path) -> list[dict[str, str]]:
    """Return Audit.csv rows still parked at relevance_status=hold."""

    rows = read_rows(audit_path, required_columns=["relevance_status"], missing_ok=True)
    return [row for row in rows if _status(row) == "hold"]


def assert_no_unresolved_holds(audit_path: str | Path) -> None:
    """Hard block hook for normalization/consolidation phases."""

    holds = unresolved_hold_rows(audit_path)
    if holds:
        raise ExtractionHoldError(holds)
