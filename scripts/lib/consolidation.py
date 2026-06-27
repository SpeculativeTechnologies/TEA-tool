"""Shared helpers for schema-driven consolidation and value review."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .csvio import (
    AUDIT_FIELDNAMES,
    MAIN_INPUT_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from .extraction import is_nullish
from .schema import GLOBAL_ENTITY_ID, Schema
from .shared_inputs import is_fixed_row, is_shared_row
from .source_url import source_url_for


DEFAULT_VALUE_DISAGREEMENT_THRESHOLD = 0.30
WORST_QUALITY_RANK = 99
ESTIMATE_QUALITY_TAG = "E"
#: Backed (E) and unbacked (U) estimates alike must clear a held-estimate verdict
#: before consolidation can trust them.
ESTIMATE_TAGS = {"E", "U"}

DISAGREEMENT_CLEAR = {"clear", "accept", "accepted", "keep", "kept"}
DISAGREEMENT_REJECT = {"reject", "rejected", "drop", "dropped"}
HELD_ESTIMATE_CLEAR = {"clear", "accept", "accepted"}
HELD_ESTIMATE_REJECT = {"reject", "rejected"}

CAPEX_OUTPUTS = (
    "capex_usd",
    "capex_form",
    "capex_basis_year",
    "capex_basis_scale",
    "capex_basis_scale_units",
    "capex_notes",
    "review_value",
    "review_units",
    "review_steps",
)


class ConsolidationError(ValueError):
    """Base class for consolidation blockers."""


class ValueDisagreementRowsError(ConsolidationError):
    """Raised when current value disagreements lack analyst decisions."""


class ScopeFitDecisionRowsError(ConsolidationError):
    """Raised when same-quality top candidates need a scope-fit decision."""


class HeldEstimateRowsError(ConsolidationError):
    """Raised when E-quality estimate rows lack review verdicts."""


class FixedInputConflictError(ConsolidationError):
    """Raised when one cell has two or more disagreeing fixed candidates."""


def cell_key(row: Mapping[str, object]) -> tuple[str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
    )


def parse_float(raw: object) -> float | None:
    if raw in (None, "", "null"):
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_year(raw: object) -> int:
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return -1


def format_number(value: float) -> str:
    return f"{value:.6g}"


def format_percent(value: float | None) -> str:
    return "" if value is None else f"{value:.1%}"


def quality_rank(tag: object, schema: Schema) -> int:
    raw = str(tag or "").strip().upper()
    if not raw:
        return WORST_QUALITY_RANK
    for idx, candidate in enumerate(schema.quality_tags):
        if raw == str(candidate).strip().upper():
            return idx
    return WORST_QUALITY_RANK


def is_capex_row(row: Mapping[str, object], schema: Schema) -> bool:
    parameter = str(row.get("parameter") or "").strip()
    return schema.has_parameter(parameter) and schema.rule_type(parameter) == "CAPEX"


def has_disagreement_decision(row: Mapping[str, object]) -> bool:
    return bool(str(row.get("disagreement_decision") or "").strip())


def disagreement_status(row: Mapping[str, object]) -> str:
    return str(row.get("disagreement_status") or "").strip().lower()


def is_disagreement_clear(row: Mapping[str, object]) -> bool:
    return disagreement_status(row) in DISAGREEMENT_CLEAR and has_disagreement_decision(row)


def is_disagreement_reject(row: Mapping[str, object]) -> bool:
    return disagreement_status(row) in DISAGREEMENT_REJECT and has_disagreement_decision(row)


def comparison_value(row: Mapping[str, object], schema: Schema) -> float | None:
    if is_capex_row(row, schema):
        return parse_float(row.get("review_value"))
    return parse_float(row.get("normalized_value"))


def comparison_units(row: Mapping[str, object], schema: Schema) -> str:
    if is_capex_row(row, schema):
        return str(row.get("review_units") or "")
    return str(row.get("normalized_units") or "")


def comparison_steps(row: Mapping[str, object], schema: Schema) -> str:
    if is_capex_row(row, schema):
        return str(row.get("review_steps") or "")
    return str(row.get("transform_steps") or "")


def has_model_value(row: Mapping[str, object], schema: Schema) -> bool:
    status = str(row.get("relevance_status") or "").strip().lower()
    if status in {"hold", "reject"}:
        return False
    if is_disagreement_reject(row):
        return False
    if is_capex_row(row, schema):
        return not is_nullish(row.get("capex_usd") or row.get("normalized_value"))
    return not is_nullish(row.get("normalized_value"))


def eligible_candidate_records(
    members: list[tuple[int, dict[str, str]]],
    schema: Schema,
) -> list[tuple[int, dict[str, str], float | None, int]]:
    records: list[tuple[int, dict[str, str], float | None, int]] = []
    for idx, row in members:
        if not has_model_value(row, schema):
            continue
        records.append((idx, row, comparison_value(row, schema), quality_rank(row.get("quality_tag"), schema)))
    return records


def has_shared_candidate(candidates: list[tuple[int, dict[str, str], float | None, int]]) -> bool:
    """Whether a cell has an authoritative shared-input candidate."""

    return any(is_shared_row(row) for _, row, _, _ in candidates)


def has_fixed_candidate(candidates: list[tuple[int, dict[str, str], float | None, int]]) -> bool:
    """Whether a cell has an authoritative fixed-input candidate."""

    return any(is_fixed_row(row) for _, row, _, _ in candidates)


def _value_signature(row: Mapping[str, object], schema: Schema) -> tuple[str, object]:
    """A comparable signature for one candidate's model value.

    Two fixed candidates ``conflict`` when their signatures differ; fixing the
    same cell twice with the same value is harmless.
    """

    cmp = comparison_value(row, schema)
    if cmp is None:
        return ("raw", str(row.get("normalized_value") or row.get("capex_usd") or "").strip())
    return ("num", round(cmp, 10))


def find_fixed_conflicts(rows: list[dict[str, str]], schema: Schema) -> list[dict[str, object]]:
    """Find cells whose eligible fixed candidates disagree (blocking in both modes)."""

    groups: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = {}
    for idx, row in enumerate(rows):
        groups.setdefault(cell_key(row), []).append((idx, row))

    conflicts: list[dict[str, object]] = []
    for key, members in sorted(groups.items()):
        candidates = eligible_candidate_records(members, schema)
        fixed = [(idx, row, cmp) for idx, row, cmp, _rank in candidates if is_fixed_row(row)]
        if len(fixed) < 2:
            continue
        signatures = {_value_signature(row, schema) for _, row, _ in fixed}
        if len(signatures) > 1:
            conflicts.append(
                {
                    "key": key,
                    "values": "; ".join(
                        f"{row.get('source_key') or 'unknown'}="
                        f"{format_number(cmp) if cmp is not None else (row.get('normalized_value') or row.get('capex_usd') or '?')}"
                        for _, row, cmp in fixed
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
        f"{len(conflicts)} cell(s) have two or more disagreeing fixed inputs. A fixed "
        "input is an authoritative user decision and cannot be auto-resolved; raise a "
        "blocking issue and have the user choose one value before consolidation.\n  "
        + "\n  ".join(lines)
        + more
    )


def fill_source_urls(
    rows: list[dict[str, str]],
    sources_path: str | Path | None,
) -> None:
    if sources_path is None:
        return
    for row in rows:
        source_key = str(row.get("source_key") or "").strip()
        if not source_key or str(row.get("source_url") or "").strip():
            continue
        row["source_url"] = source_url_for(source_key, sources_path, required=True)


def validate_audit_cells(rows: list[dict[str, str]], schema: Schema) -> None:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        entity, parameter = cell_key(row)
        if not entity and not parameter:
            continue
        if not schema.has_parameter(parameter):
            errors.append(f"row {idx}: unknown parameter {parameter!r}")
            continue
        if entity == GLOBAL_ENTITY_ID:
            if not schema.applies(parameter, entity):
                errors.append(f"row {idx}: parameter {parameter!r} is not a reference value")
        elif not schema.has_entity(entity):
            errors.append(f"row {idx}: unknown entity {entity!r}")
        elif not schema.applies(parameter, entity):
            errors.append(f"row {idx}: parameter {parameter!r} does not apply to entity {entity!r}")
    if errors:
        raise ConsolidationError("\n".join(errors))


def active_numeric_rows(
    rows: list[dict[str, str]],
    schema: Schema,
) -> list[tuple[int, dict[str, str], float]]:
    out: list[tuple[int, dict[str, str], float]] = []
    for idx, row in enumerate(rows):
        status = str(row.get("relevance_status") or "").strip().lower()
        if status in {"hold", "reject"}:
            continue
        if is_disagreement_reject(row):
            continue
        value = comparison_value(row, schema)
        if value is None:
            continue
        out.append((idx, row, value))
    return out


def find_value_disagreements(
    rows: list[dict[str, str]],
    schema: Schema,
    threshold: float = DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[tuple[int, dict[str, str], float]]] = {}
    for idx, row, value in active_numeric_rows(rows, schema):
        groups.setdefault(cell_key(row), []).append((idx, row, value))

    held: list[dict[str, object]] = []
    for (entity, parameter), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        # A shared or fixed candidate is authoritative for its cell; contrary
        # evidence is recorded but does not block via the disagreement gate.
        if any(is_shared_row(row) or is_fixed_row(row) for _, row, _ in members):
            continue
        values = [value for _, _, value in members]
        avg = sum(values) / len(values)
        denom = abs(avg)
        group_values = "; ".join(
            f"{row.get('source_key') or 'unknown'}={format_number(value)}"
            for _, row, value in members
        )
        for idx, row, value in members:
            if is_disagreement_clear(row) or is_disagreement_reject(row):
                continue
            if denom == 0:
                pct = None
                flagged = value != 0
            else:
                pct = abs(value - avg) / denom
                flagged = pct >= threshold
            if not flagged:
                continue
            held.append(
                {
                    "row_index": idx,
                    "entity": entity,
                    "parameter": parameter,
                    "source_key": row.get("source_key", ""),
                    "source_url": row.get("source_url", ""),
                    "quality_tag": row.get("quality_tag", ""),
                    "comparison_value": value,
                    "comparison_units": comparison_units(row, schema),
                    "comparison_steps": comparison_steps(row, schema),
                    "group_average": avg,
                    "percent_from_average": pct,
                    "group_count": len(members),
                    "group_min": min(values),
                    "group_max": max(values),
                    "group_values": group_values,
                    "row": row,
                }
            )
    return held


def format_value_disagreement_error(
    disagreements: list[dict[str, object]],
    threshold: float = DEFAULT_VALUE_DISAGREEMENT_THRESHOLD,
) -> str:
    lines: list[str] = []
    for item in disagreements[:10]:
        pct = format_percent(item.get("percent_from_average")) or "undefined %"
        lines.append(
            "row {row_index} ({entity},{parameter} from {source_key}): "
            "{value} vs avg {avg} ({pct})".format(
                row_index=int(item["row_index"]) + 2,
                entity=item["entity"],
                parameter=item["parameter"],
                source_key=item["source_key"],
                value=format_number(float(item["comparison_value"])),
                avg=format_number(float(item["group_average"])),
                pct=pct,
            )
        )
    more = "" if len(disagreements) <= 10 else f"\n  ... +{len(disagreements) - 10} more"
    return (
        f"{len(disagreements)} normalized row(s) differ from their same "
        f"(entity, parameter) average by >= {threshold:.0%} and need Phase 4.3 "
        "review. Run sweep_value_disagreements.py, answer the queue, then "
        "apply_value_disagreements.py before consolidation.\n  "
        + "\n  ".join(lines)
        + more
    )


def find_unresolved_held_estimates(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    unresolved: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=2):
        if str(row.get("quality_tag") or "").strip().upper() not in ESTIMATE_TAGS:
            continue
        if str(row.get("relevance_status") or "").strip().lower() == "reject":
            continue
        if is_nullish(row.get("normalized_value")) and is_nullish(row.get("capex_usd")):
            continue
        status = str(row.get("held_estimate_status") or "").strip().lower()
        if status in HELD_ESTIMATE_CLEAR or status in HELD_ESTIMATE_REJECT:
            continue
        unresolved.append(
            {
                "row_index": idx,
                "entity": row.get("entity", ""),
                "parameter": row.get("parameter", ""),
                "source_key": row.get("source_key", ""),
            }
        )
    return unresolved


def format_held_estimate_error(unresolved: list[dict[str, object]]) -> str:
    lines = [
        f"row {r['row_index']} ({r['entity']},{r['parameter']} from {r['source_key']})"
        for r in unresolved[:10]
    ]
    more = "" if len(unresolved) <= 10 else f"\n  ... +{len(unresolved) - 10} more"
    return (
        f"{len(unresolved)} estimate row(s) (quality_tag E/U) lack a held-estimate "
        "verdict. Run sweep_held_estimates.py and apply_held_estimates.py before "
        "consolidation.\n  "
        + "\n  ".join(lines)
        + more
    )


def find_scope_fit_decision_problems(
    rows: list[dict[str, str]],
    schema: Schema,
    decisions: Mapping[tuple[str, str], str],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = {}
    for idx, row in enumerate(rows):
        groups.setdefault(cell_key(row), []).append((idx, row))

    problems: list[dict[str, object]] = []
    for key, members in sorted(groups.items()):
        candidates = eligible_candidate_records(members, schema)
        if not candidates:
            continue
        if has_shared_candidate(candidates) or has_fixed_candidate(candidates):
            continue
        top_rank = min(rank for _, _, _, rank in candidates)
        top_keys = sorted(
            {
                str(row.get("source_key") or "").strip()
                for _, row, _, rank in candidates
                if rank == top_rank and str(row.get("source_key") or "").strip()
            }
        )
        if len(top_keys) <= 1:
            continue
        selected = str(decisions.get(key) or "").strip()
        if not selected:
            problems.append({"kind": "missing", "key": key, "candidates": top_keys})
        elif selected not in top_keys:
            problems.append(
                {"kind": "invalid", "key": key, "selected": selected, "candidates": top_keys}
            )
    return problems


def format_scope_fit_error(problems: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for problem in problems[:10]:
        entity, parameter = problem["key"]
        candidates = ", ".join(problem["candidates"])
        if problem["kind"] == "missing":
            lines.append(f"({entity},{parameter}): needs decision among [{candidates}]")
        else:
            lines.append(
                f"({entity},{parameter}): decision {problem['selected']!r} is not one of [{candidates}]"
            )
    more = "" if len(problems) <= 10 else f"\n  ... +{len(problems) - 10} more"
    return (
        f"{len(problems)} same-quality top candidate group(s) need a Phase 4.4 "
        "scope-fit decision before recency/source_key fallback. Run "
        "prompts/scope-fit-agent.md and provide stage5_scope_fit_decisions.csv.\n  "
        + "\n  ".join(lines)
        + more
    )


def select_rows(
    rows: list[dict[str, str]],
    schema: Schema,
    scope_fit_decisions: Mapping[tuple[str, str], str] | None = None,
) -> list[dict[str, str]]:
    scope_fit_decisions = scope_fit_decisions or {}
    out = [dict(row) for row in rows]
    groups: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = {}
    for idx, row in enumerate(out):
        groups.setdefault(cell_key(row), []).append((idx, row))

    for row in out:
        row["selected_for_model"] = ""
        row["cross_check_delta"] = ""

    for key, members in groups.items():
        candidates = eligible_candidate_records(members, schema)
        if not candidates:
            continue

        # Selection precedence (orchestrator §6): a fixed candidate (any origin)
        # outranks an approved shared input, which outranks ordinary candidates.
        fixed = [candidate for candidate in candidates if is_fixed_row(candidate[1])]
        if len(fixed) > 1 and len({_value_signature(row, schema) for _, row, _, _ in fixed}) > 1:
            raise FixedInputConflictError(
                format_fixed_conflict_error(find_fixed_conflicts([row for _, row in members], schema))
            )
        shared = [candidate for candidate in candidates if is_shared_row(candidate[1])]
        active = fixed or shared or candidates
        top_rank = min(rank for _, _, _, rank in active)
        selected_by_scope = str(scope_fit_decisions.get(key) or "").strip()

        def sort_key(candidate: tuple[int, dict[str, str], float | None, int]) -> tuple[int, int, int, str]:
            _, row, _, rank = candidate
            source_key = str(row.get("source_key") or "").strip()
            scope_bias = 0
            if selected_by_scope and rank == top_rank:
                scope_bias = 0 if source_key == selected_by_scope else 1
            return (
                rank,
                scope_bias,
                -parse_year(row.get("raw_basis_year")),
                source_key,
            )

        active.sort(key=sort_key)
        selected_idx, _, selected_cmp, _ = active[0]
        out[selected_idx]["selected_for_model"] = "TRUE"

        deltas: list[str] = []
        if selected_cmp not in (None, 0):
            for idx, runner, runner_cmp, _ in candidates:
                if idx == selected_idx:
                    continue
                if runner_cmp is None:
                    continue
                delta = (runner_cmp - selected_cmp) / selected_cmp
                deltas.append(f"{delta:+.0%} vs [{runner.get('source_key') or 'unknown'}]")
        if deltas:
            out[selected_idx]["cross_check_delta"] = "; ".join(deltas)

        for idx, _, _, _ in candidates:
            if idx != selected_idx:
                out[idx]["selected_for_model"] = "FALSE"

    return out


def main_input_row(
    entity: str,
    parameter: str,
    selected: Mapping[str, object] | None,
) -> dict[str, str]:
    row = blank_row(MAIN_INPUT_FIELDNAMES)
    row["entity"] = entity
    row["parameter"] = parameter
    if selected is None:
        row["notes"] = (
            "no reference value - context-free search candidate"
            if entity == GLOBAL_ENTITY_ID
            else "no data - gap-fill candidate"
        )
        return row

    copied = (
        "raw_value",
        "raw_units",
        "raw_basis_scale",
        "raw_basis_scale_units",
        "raw_basis_year",
        "normalized_value",
        "normalized_units",
        "capex_usd",
        "capex_form",
        "capex_basis_year",
        "capex_basis_scale",
        "capex_basis_scale_units",
        "capex_notes",
        "review_value",
        "review_units",
        "review_steps",
        "quality_tag",
        "source_key",
        "source_url",
        "page_ref",
        "cross_check_delta",
        "estimate_justification",
        "input_origin",
        "input_priority",
    )
    for key in copied:
        row[key] = str(selected.get(key) or "")
    note_parts = [
        str(selected.get("notes") or "").strip(),
        str(selected.get("transform_steps") or "").strip(),
    ]
    row["notes"] = " | ".join(part for part in note_parts if part)
    return row


def build_main_input_rows(rows: list[dict[str, str]], schema: Schema) -> list[dict[str, str]]:
    selected: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if str(row.get("selected_for_model") or "").strip().upper() == "TRUE":
            selected[cell_key(row)] = row
    return [
        main_input_row(entity, parameter, selected.get((entity, parameter)))
        for entity, parameter in schema.skeleton_cells()
    ]


def main_row_has_value(row: Mapping[str, object]) -> bool:
    return any(not is_nullish(row.get(key)) for key in ("normalized_value", "capex_usd"))


def write_audit_rows(path: str | Path, rows: list[dict[str, str]]) -> int:
    return write_rows(path, AUDIT_FIELDNAMES, rows)


def write_main_input_rows(path: str | Path, rows: list[dict[str, str]]) -> int:
    return write_rows(path, MAIN_INPUT_FIELDNAMES, rows)


def read_audit_rows(path: str | Path) -> list[dict[str, str]]:
    return read_rows(path, required_columns=AUDIT_FIELDNAMES)
