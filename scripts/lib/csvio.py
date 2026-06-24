"""Shared CSV schemas and stable read/write helpers for the TEA pipeline.

The deterministic scripts all exchange rows through a small set of CSV files.
This module is the single place where their column order lives, so downstream
lanes can add behavior without quietly drifting the contract. The schemas use
the neutral vocabulary from D13: ``entity`` and ``parameter``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CsvColumn:
    """One CSV column in the deterministic contract."""

    name: str
    description: str = ""


def column_names(schema: Sequence[CsvColumn | str]) -> list[str]:
    """Return just the field names for a schema definition."""

    names: list[str] = []
    for col in schema:
        names.append(col.name if isinstance(col, CsvColumn) else str(col))
    return names


SOURCES_COLUMNS = [
    CsvColumn("source_key", "Short stable id; primary key."),
    CsvColumn("authors", "Source authors, organizations, or empty if unknown."),
    CsvColumn("title", "Source title."),
    CsvColumn("year", "Publication or data year."),
    CsvColumn("publisher_or_journal", "Publisher, journal, agency, or venue."),
    CsvColumn("source_url", "Canonical URL. Replaces Vicky TEA's url_or_doi."),
    CsvColumn("doi", "Optional DOI when distinct from source_url."),
    CsvColumn("access_date", "Date the source was accessed, ISO YYYY-MM-DD preferred."),
    CsvColumn("page_or_table_reference", "Whole-source anchor; row anchors live in Audit.page_ref."),
    CsvColumn("source_role", "extraction, estimate, both, or analyst."),
    CsvColumn("notes", "Registration notes."),
]


AUDIT_COLUMNS = [
    CsvColumn("entity", "Schema entity id, or REF for reference values."),
    CsvColumn("parameter", "Schema parameter id."),
    CsvColumn("source_key", "Foreign key to Sources.csv."),
    CsvColumn("source_url", "Denormalized from Sources.csv whenever source_key is written."),
    CsvColumn("page_ref", "Page, table, figure, equation, or n/a for estimates."),
    CsvColumn("raw_value", "Value exactly as the source reports it."),
    CsvColumn("raw_units", "Units exactly as the source reports them."),
    CsvColumn("raw_basis_scale", "Scale basis exactly as extracted, if any."),
    CsvColumn("raw_basis_scale_units", "Units for raw_basis_scale."),
    CsvColumn("raw_basis_year", "Source-year or cost basis year."),
    CsvColumn("quality_tag", "A/B/C/D/E or the configured quality tag."),
    CsvColumn("normalized_value", "Model-ready value after rule-type normalization."),
    CsvColumn("normalized_units", "Model-ready units after rule-type normalization."),
    CsvColumn("transform_steps", "Normalizer audit trail."),
    CsvColumn("capex_usd", "CAPEX converted to source-year USD."),
    CsvColumn("capex_form", "CAPEX form, e.g. total or specific_per_annual_output."),
    CsvColumn("capex_basis_year", "Dollar basis year carried for CAPEX."),
    CsvColumn("capex_basis_scale", "CAPEX scale basis, carried without hardcoded units."),
    CsvColumn("capex_basis_scale_units", "Units for capex_basis_scale."),
    CsvColumn("capex_notes", "CAPEX parsing and carry-forward notes."),
    CsvColumn("review_value", "QA-only comparable value."),
    CsvColumn("review_units", "Units for review_value."),
    CsvColumn("review_steps", "QA-only comparison transform trail."),
    CsvColumn("selected_for_model", "TRUE on the consolidated row selected for its cell."),
    CsvColumn("cross_check_delta", "Cross-source disagreement annotation."),
    CsvColumn("extractor_notes", "Extractor caveats and provenance notes."),
    CsvColumn("relevance_status", "clear, hold, or reject."),
    CsvColumn("input_origin", "extracted, shared, estimated, or analyst."),
    CsvColumn("input_priority", "fixed (validated authoritative user decision) or blank."),
    CsvColumn("analyst_question", "Self-contained question for held rows."),
    CsvColumn("normalization_status", "Status for Phase 4.2 normalization flags."),
    CsvColumn("normalization_decision", "Analyst/agent answer for normalization flags."),
    CsvColumn("disagreement_status", "Status for Phase 4.3 disagreement review."),
    CsvColumn("disagreement_decision", "Analyst decision for disagreement review."),
    CsvColumn("estimate_justification", "Structured JSON for E-quality estimates."),
    CsvColumn("held_estimate_status", "Status for Phase 6.2 held-estimate review."),
    CsvColumn("held_estimate_answer", "Analyst answer for held estimates."),
    CsvColumn("notes", "Free-form pipeline notes."),
]


MAIN_INPUT_COLUMNS = [
    CsvColumn("entity", "Schema entity id, or REF for reference values."),
    CsvColumn("parameter", "Schema parameter id."),
    CsvColumn("raw_value", "Selected source value exactly as extracted."),
    CsvColumn("raw_units", "Selected source units exactly as extracted."),
    CsvColumn("raw_basis_scale", "Selected source basis scale exactly as extracted."),
    CsvColumn("raw_basis_scale_units", "Selected source basis-scale units."),
    CsvColumn("raw_basis_year", "Selected source basis year exactly as extracted."),
    CsvColumn("normalized_value", "Selected normalized value."),
    CsvColumn("normalized_units", "Selected normalized units."),
    CsvColumn("capex_usd", "Selected CAPEX source-year USD value."),
    CsvColumn("capex_form", "Selected CAPEX form."),
    CsvColumn("capex_basis_year", "Selected CAPEX dollar basis year."),
    CsvColumn("capex_basis_scale", "Selected CAPEX scale basis."),
    CsvColumn("capex_basis_scale_units", "Units for selected CAPEX scale basis."),
    CsvColumn("capex_notes", "Selected CAPEX notes."),
    CsvColumn("review_value", "QA-only comparable value."),
    CsvColumn("review_units", "Units for review_value."),
    CsvColumn("review_steps", "QA-only comparison transform trail."),
    CsvColumn("quality_tag", "Quality tag of the selected row."),
    CsvColumn("source_key", "Foreign key to Sources.csv."),
    CsvColumn("source_url", "Denormalized from Sources.csv whenever source_key is written."),
    CsvColumn("page_ref", "Selected row page/table/figure anchor."),
    CsvColumn("cross_check_delta", "Cross-source disagreement annotation."),
    CsvColumn("estimate_justification", "Structured JSON propagated from selected E rows."),
    CsvColumn("input_origin", "extracted, shared, estimated, or analyst."),
    CsvColumn("input_priority", "fixed (validated authoritative user decision) or blank."),
    CsvColumn("notes", "Residual gap, shared-input, or consolidation notes."),
]


HELD_QUESTIONS_COLUMNS = [
    CsvColumn("entity"),
    CsvColumn("parameter"),
    CsvColumn("source_key"),
    CsvColumn("source_url"),
    CsvColumn("page_ref"),
    CsvColumn("raw_value"),
    CsvColumn("raw_units"),
    CsvColumn("relevance_status"),
    CsvColumn("analyst_question"),
    CsvColumn("extractor_notes"),
    CsvColumn("proposed_verdict"),
    CsvColumn("analyst_answer"),
    CsvColumn("notes"),
]


NORMALIZATION_FLAGS_COLUMNS = [
    CsvColumn("entity"),
    CsvColumn("parameter"),
    CsvColumn("source_key"),
    CsvColumn("source_url"),
    CsvColumn("raw_value"),
    CsvColumn("raw_units"),
    CsvColumn("normalized_value"),
    CsvColumn("normalized_units"),
    CsvColumn("flag_reason"),
    CsvColumn("proposed_action"),
    CsvColumn("analyst_answer"),
    CsvColumn("notes"),
]


VALUE_DISAGREEMENTS_COLUMNS = [
    CsvColumn("entity"),
    CsvColumn("parameter"),
    CsvColumn("source_key"),
    CsvColumn("source_url"),
    CsvColumn("normalized_value"),
    CsvColumn("normalized_units"),
    CsvColumn("quality_tag"),
    CsvColumn("cross_check_delta"),
    CsvColumn("disagreement_group"),
    CsvColumn("proposed_verdict"),
    CsvColumn("analyst_answer"),
    CsvColumn("notes"),
]


SCOPE_FIT_DECISIONS_COLUMNS = [
    CsvColumn("entity"),
    CsvColumn("parameter"),
    CsvColumn("source_key"),
    CsvColumn("source_url"),
    CsvColumn("quality_tag"),
    CsvColumn("normalized_value"),
    CsvColumn("normalized_units"),
    CsvColumn("scope_fit_question"),
    CsvColumn("decision"),
    CsvColumn("rationale"),
    CsvColumn("notes"),
]


HELD_ESTIMATES_COLUMNS = [
    CsvColumn("entity"),
    CsvColumn("parameter"),
    CsvColumn("source_key"),
    CsvColumn("source_url"),
    CsvColumn("raw_value"),
    CsvColumn("raw_units"),
    CsvColumn("normalized_value"),
    CsvColumn("normalized_units"),
    CsvColumn("estimate_justification"),
    CsvColumn("held_estimate_status"),
    CsvColumn("proposed_verdict"),
    CsvColumn("analyst_value"),
    CsvColumn("analyst_units"),
    CsvColumn("analyst_answer"),
    CsvColumn("notes"),
]


SHARED_INPUTS_COLUMNS = [
    CsvColumn("shared_input_id", "Stable id for a reusable comparison assumption."),
    CsvColumn("raw_value", "Shared value exactly as supplied by the analyst/source."),
    CsvColumn("raw_units", "Units for raw_value."),
    CsvColumn("raw_basis_scale", "Scale basis, if any."),
    CsvColumn("raw_basis_scale_units", "Units for raw_basis_scale."),
    CsvColumn("raw_basis_year", "Source-year or cost basis year."),
    CsvColumn("source_key", "Stable provenance key for this shared value."),
    CsvColumn("page_ref", "Page, table, figure, equation, or analyst note anchor."),
    CsvColumn("quality_tag", "Optional A/B/C/D tag for the shared evidence."),
    CsvColumn("notes", "Why this value is reusable or any carry-forward context."),
]


SHARED_INPUT_MAPPINGS_COLUMNS = [
    CsvColumn("shared_input_id", "Shared input id from shared-inputs.csv."),
    CsvColumn("option_id", "Comparison option id from comparison-frame.json."),
    CsvColumn("entity", "Target option schema entity id, or REF for reference values."),
    CsvColumn("parameter", "Target option schema parameter id."),
    CsvColumn("notes", "Analyst rationale for applying this shared input to the target cell."),
]


# Analyst-supplied inputs (orchestrator §6). ``user-sources.csv`` reuses the
# source-registry shape (and may carry ``source_role=analyst``); ``user-inputs.csv``
# holds only values the analyst mapped to a real schema cell. The two-axis
# classification keeps the plan's vocabulary explicit: ``input_origin`` records
# the lane (analyst assertion vs uploaded-doc extraction vs shared assumption),
# while ``fixed`` records whether the user fixed it as authoritative.
USER_INPUTS_COLUMNS = [
    CsvColumn("input_id", "Stable id for one analyst-supplied mapped value."),
    CsvColumn("entity", "Target schema entity id, or REF for reference values."),
    CsvColumn("parameter", "Target schema parameter id."),
    CsvColumn("raw_value", "Value exactly as the user or source supplied it."),
    CsvColumn("raw_units", "Units for raw_value."),
    CsvColumn("raw_basis_scale", "Scale basis, if any."),
    CsvColumn("raw_basis_scale_units", "Units for raw_basis_scale."),
    CsvColumn("raw_basis_year", "Source-year or cost basis year."),
    CsvColumn("source_key", "Foreign key to user-sources.csv / Sources.csv."),
    CsvColumn("page_ref", "Precise sheet/cell, page, table, or decision-log reference."),
    CsvColumn("quality_tag", "Quality tag for the supplied value."),
    CsvColumn("input_origin", "analyst, extracted, or shared (the input classification / lane)."),
    CsvColumn("fixed", "TRUE for a fixed input (authoritative); blank for candidate evidence."),
    CsvColumn("notes", "Pipeline notes."),
    CsvColumn("user_rationale", "Why the user supplied or fixed this value."),
]


CSV_SCHEMAS = {
    "Sources.csv": SOURCES_COLUMNS,
    "Audit.csv": AUDIT_COLUMNS,
    "Main Input.csv": MAIN_INPUT_COLUMNS,
    "held_questions.csv": HELD_QUESTIONS_COLUMNS,
    "normalization_flags.csv": NORMALIZATION_FLAGS_COLUMNS,
    "value_disagreements.csv": VALUE_DISAGREEMENTS_COLUMNS,
    "stage5_scope_fit_decisions.csv": SCOPE_FIT_DECISIONS_COLUMNS,
    "held_estimates.csv": HELD_ESTIMATES_COLUMNS,
    "shared-inputs.csv": SHARED_INPUTS_COLUMNS,
    "shared-input-mappings.csv": SHARED_INPUT_MAPPINGS_COLUMNS,
    "user-sources.csv": SOURCES_COLUMNS,
    "user-inputs.csv": USER_INPUTS_COLUMNS,
}


SOURCES_FIELDNAMES = column_names(SOURCES_COLUMNS)
AUDIT_FIELDNAMES = column_names(AUDIT_COLUMNS)
MAIN_INPUT_FIELDNAMES = column_names(MAIN_INPUT_COLUMNS)
SHARED_INPUTS_FIELDNAMES = column_names(SHARED_INPUTS_COLUMNS)
SHARED_INPUT_MAPPINGS_FIELDNAMES = column_names(SHARED_INPUT_MAPPINGS_COLUMNS)
USER_INPUTS_FIELDNAMES = column_names(USER_INPUTS_COLUMNS)
USER_SOURCES_FIELDNAMES = SOURCES_FIELDNAMES


def blank_row(fieldnames: Sequence[str]) -> dict[str, str]:
    """Return an all-empty row with exactly the requested fieldnames."""

    return {name: "" for name in fieldnames}


def ordered_row(row: Mapping[str, object], fieldnames: Sequence[str]) -> dict[str, str]:
    """Project ``row`` into ``fieldnames`` order, coercing ``None`` to empty."""

    out: dict[str, str] = {}
    for name in fieldnames:
        value = row.get(name, "")
        out[name] = "" if value is None else str(value)
    return out


def _unknown_keys(row: Mapping[str, object], fieldnames: Sequence[str]) -> list[str]:
    allowed = set(fieldnames)
    return [key for key in row if key not in allowed]


def write_rows(
    path: str | Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]] = (),
    *,
    extras_action: str = "raise",
) -> int:
    """Write rows with stable column ordering and return the number written.

    ``extras_action`` matches ``csv.DictWriter`` semantics for unknown keys:
    ``"raise"`` rejects them, while ``"ignore"`` projects them away.
    """

    if extras_action not in {"raise", "ignore"}:
        raise ValueError("extras_action must be 'raise' or 'ignore'")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            unknown = _unknown_keys(row, fieldnames)
            if unknown and extras_action == "raise":
                raise ValueError(f"{path}: row has unknown column(s): {unknown!r}")
            writer.writerow(ordered_row(row, fieldnames))
            count += 1
    return count


def read_rows(
    path: str | Path,
    *,
    required_columns: Sequence[str] | None = None,
    missing_ok: bool = False,
) -> list[dict[str, str]]:
    """Read a CSV into dictionaries, optionally validating required columns."""

    path = Path(path)
    if missing_ok and not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        if required_columns:
            missing = [col for col in required_columns if col not in fieldnames]
            if missing:
                raise ValueError(f"{path}: missing required column(s): {missing!r}")
        return [dict(row) for row in reader]


def read_header(path: str | Path, *, missing_ok: bool = False) -> list[str]:
    """Read only the header row from a CSV."""

    path = Path(path)
    if missing_ok and not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            return next(reader)
        except StopIteration:
            return []


def append_rows(
    path: str | Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
    *,
    extras_action: str = "raise",
) -> int:
    """Append rows, creating the file with ``fieldnames`` if needed."""

    if extras_action not in {"raise", "ignore"}:
        raise ValueError("extras_action must be 'raise' or 'ignore'")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_header = read_header(path, missing_ok=True)
    active_fieldnames = existing_header or list(fieldnames)
    if existing_header:
        missing = [name for name in fieldnames if name not in existing_header]
        if missing:
            raise ValueError(f"{path}: existing header is missing expected column(s): {missing!r}")

    count = 0
    needs_header = not existing_header
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=active_fieldnames, extrasaction="ignore")
        if needs_header:
            writer.writeheader()
        for row in rows:
            unknown = _unknown_keys(row, active_fieldnames)
            if unknown and extras_action == "raise":
                raise ValueError(f"{path}: row has unknown column(s): {unknown!r}")
            writer.writerow(ordered_row(row, active_fieldnames))
            count += 1
    return count


def file_is_nonempty(path: str | Path) -> bool:
    """Whether a path exists and has bytes on disk."""

    path = Path(path)
    return path.exists() and path.stat().st_size > 0
