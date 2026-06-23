"""Shared pinned-input helpers.

Pinned cells are authoritative analyst-provided values. They enter the normal
Audit flow with ``relevance_status=pinned`` and are marked on Main Input
skeleton rows so search, extraction, and estimation can skip them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from .csvio import AUDIT_FIELDNAMES, MAIN_INPUT_FIELDNAMES, read_rows
from .schema import GLOBAL_ENTITY_ID, Schema


PINNED_STATUS = "pinned"


def truthy(value: object) -> bool:
    """Return whether a CSV-ish value means true."""

    return str(value or "").strip().upper() in {"TRUE", "YES", "Y", "1"}


def cell_key(row: Mapping[str, object]) -> tuple[str, str]:
    """Return the normalized ``(entity, parameter)`` key for a row."""

    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
    )


def is_pinned_row(row: Mapping[str, object]) -> bool:
    """Whether a row represents a locked pinned cell."""

    return (
        str(row.get("relevance_status") or "").strip().lower() == PINNED_STATUS
        or truthy(row.get("pinned"))
    )


def validate_cell(schema: Schema, entity: str, parameter: str, *, row_label: str = "row") -> None:
    """Validate one pinned cell against the schema skeleton."""

    if not entity:
        raise ValueError(f"{row_label}: entity is required")
    if not parameter:
        raise ValueError(f"{row_label}: parameter is required")
    if not schema.has_parameter(parameter):
        raise ValueError(f"{row_label}: unknown parameter {parameter!r}")
    if entity == GLOBAL_ENTITY_ID:
        if not schema.applies(parameter, entity):
            raise ValueError(
                f"{row_label}: parameter {parameter!r} is not a reference value for {GLOBAL_ENTITY_ID}"
            )
        return
    if not schema.has_entity(entity):
        raise ValueError(f"{row_label}: unknown entity {entity!r}")
    if not schema.applies(parameter, entity):
        raise ValueError(
            f"{row_label}: parameter {parameter!r} does not apply to entity {entity!r}"
        )


def validate_cells(schema: Schema, cells: Iterable[tuple[str, str]]) -> None:
    """Validate an iterable of cells, collecting all errors."""

    errors: list[str] = []
    for idx, (entity, parameter) in enumerate(cells, start=1):
        try:
            validate_cell(schema, entity, parameter, row_label=f"cell {idx}")
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))


def pinned_cells_from_rows(rows: Iterable[Mapping[str, object]]) -> set[tuple[str, str]]:
    """Return all pinned cell keys in a row collection."""

    return {cell_key(row) for row in rows if is_pinned_row(row)}


def read_pinned_cells(
    *,
    main_input_path: str | Path | None = "Main Input.csv",
    audit_path: str | Path | None = "Audit.csv",
) -> set[tuple[str, str]]:
    """Read pinned cells from Main Input and/or Audit if those files exist."""

    cells: set[tuple[str, str]] = set()
    if main_input_path is not None:
        rows = read_rows(
            main_input_path,
            required_columns=["entity", "parameter", "pinned"],
            missing_ok=True,
        )
        cells.update(pinned_cells_from_rows(rows))
    if audit_path is not None:
        rows = read_rows(
            audit_path,
            required_columns=["entity", "parameter", "relevance_status"],
            missing_ok=True,
        )
        cells.update(pinned_cells_from_rows(rows))
    return cells


def row_is_pinned_cell(row: Mapping[str, object], cells: set[tuple[str, str]]) -> bool:
    """Whether a row's cell is in the provided pinned-cell set."""

    return cell_key(row) in cells


def assert_required_headers_available() -> None:
    """Import-time guard that schemas still expose the columns T8 depends on."""

    for required in ("entity", "parameter", "relevance_status"):
        if required not in AUDIT_FIELDNAMES:
            raise AssertionError(f"Audit.csv schema is missing {required!r}")
    for required in ("entity", "parameter", "pinned"):
        if required not in MAIN_INPUT_FIELDNAMES:
            raise AssertionError(f"Main Input.csv schema is missing {required!r}")


assert_required_headers_available()
