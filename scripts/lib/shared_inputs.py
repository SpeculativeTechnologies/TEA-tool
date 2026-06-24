"""Shared-input helpers for comparison projects.

Shared inputs are analyst-approved reusable evidence rows. They enter normal
option runs as ``relevance_status=clear`` with ``input_origin=shared`` so the
single-TEA pipeline can skip already-satisfied cells without a separate lock
status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from .csvio import AUDIT_FIELDNAMES, MAIN_INPUT_FIELDNAMES, read_rows
from .schema import GLOBAL_ENTITY_ID, Schema


SHARED_ORIGIN = "shared"
ESTIMATED_ORIGIN = "estimated"
EXTRACTED_ORIGIN = "extracted"
ANALYST_ORIGIN = "analyst"
INPUT_ORIGINS = {EXTRACTED_ORIGIN, SHARED_ORIGIN, ESTIMATED_ORIGIN, ANALYST_ORIGIN}

#: ``input_priority`` value marking a validated authoritative user decision.
FIXED_PRIORITY = "fixed"


def cell_key(row: Mapping[str, object]) -> tuple[str, str]:
    """Return the normalized ``(entity, parameter)`` key for a row."""

    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
    )


def input_origin(row: Mapping[str, object]) -> str:
    """Return a normalized input origin value."""

    return str(row.get("input_origin") or "").strip().lower()


def input_priority(row: Mapping[str, object]) -> str:
    """Return a normalized input priority value (``fixed`` or blank)."""

    return str(row.get("input_priority") or "").strip().lower()


def is_shared_row(row: Mapping[str, object]) -> bool:
    """Whether a row came from the comparison shared-input library."""

    return input_origin(row) == SHARED_ORIGIN


def is_fixed_row(row: Mapping[str, object]) -> bool:
    """Whether a row is a fixed input (authoritative user decision, any origin)."""

    return input_priority(row) == FIXED_PRIORITY


def validate_cell(schema: Schema, entity: str, parameter: str, *, row_label: str = "row") -> None:
    """Validate one mapped target cell against an option schema skeleton."""

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
    """Validate an iterable of target cells, collecting all errors."""

    errors: list[str] = []
    for idx, (entity, parameter) in enumerate(cells, start=1):
        try:
            validate_cell(schema, entity, parameter, row_label=f"cell {idx}")
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))


def shared_cells_from_rows(rows: Iterable[Mapping[str, object]]) -> set[tuple[str, str]]:
    """Return all shared-origin cell keys in a row collection."""

    return {cell_key(row) for row in rows if is_shared_row(row)}


def satisfied_cells_from_rows(rows: Iterable[Mapping[str, object]]) -> set[tuple[str, str]]:
    """Return cell keys that suppress further research.

    A cell is satisfied when it carries a shared input or a fixed input.
    Non-fixed analyst (or extracted/estimated) candidate evidence does **not**
    satisfy a cell — normal research still proceeds for it (orchestrator §6).
    """

    return {cell_key(row) for row in rows if is_shared_row(row) or is_fixed_row(row)}


def read_satisfied_cells(
    *,
    main_input_path: str | Path | None = "Main Input.csv",
    audit_path: str | Path | None = "Audit.csv",
) -> set[tuple[str, str]]:
    """Read cells already satisfied by shared or fixed inputs from Main Input/Audit."""

    cells: set[tuple[str, str]] = set()
    for path in (main_input_path, audit_path):
        if path is None:
            continue
        rows = read_rows(
            path,
            required_columns=["entity", "parameter", "input_origin"],
            missing_ok=True,
        )
        cells.update(satisfied_cells_from_rows(rows))
    return cells


def row_is_satisfied_cell(row: Mapping[str, object], cells: set[tuple[str, str]]) -> bool:
    """Whether a row's cell is in the provided satisfied-cell set."""

    return cell_key(row) in cells


def assert_required_headers_available() -> None:
    """Import-time guard that CSV schemas expose the columns shared inputs need."""

    for required in ("entity", "parameter", "input_origin"):
        if required not in AUDIT_FIELDNAMES:
            raise AssertionError(f"Audit.csv schema is missing {required!r}")
    for required in ("entity", "parameter", "input_origin"):
        if required not in MAIN_INPUT_FIELDNAMES:
            raise AssertionError(f"Main Input.csv schema is missing {required!r}")


assert_required_headers_available()
