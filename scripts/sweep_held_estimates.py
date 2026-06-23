"""Collect unresolved E-quality estimates into held_estimates.csv.

Every estimate row is analyst-reviewed before it can be trusted downstream.
The queue preserves source URLs and carries compact method/citation notes so
the analyst can mark ``accept``, ``reject``, or ``analyst-override``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

from lib.csvio import CSV_SCHEMAS, column_names, read_rows, write_rows
from lib.source_url import SourceUrlError, source_url_for


HELD_ESTIMATES_FIELDNAMES = column_names(CSV_SCHEMAS["held_estimates.csv"])
ESTIMATE_QUALITY_TAG = "E"
ANSWER_FIELDS = ("proposed_verdict", "analyst_value", "analyst_units", "analyst_answer", "notes")
RESOLVED_STATUSES = {"clear", "accept", "accepted", "reject", "rejected"}


def _estimate_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("entity") or "").strip(),
        str(row.get("parameter") or "").strip(),
        str(row.get("source_key") or "").strip(),
        str(row.get("raw_value") or "").strip(),
        str(row.get("normalized_value") or row.get("capex_usd") or "").strip(),
    )


def _parse_justification(row: Mapping[str, object]) -> dict:
    raw = row.get("estimate_justification")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _source_keys_from_justification(justification: Mapping[str, object]) -> list[str]:
    keys: list[str] = []

    def add(value: object) -> None:
        key = str(value or "").strip()
        if key and key not in keys:
            keys.append(key)

    for source in justification.get("cited_sources") or []:
        if isinstance(source, Mapping):
            add(source.get("source_key") or source.get("key"))
    comparable = justification.get("comparable")
    if isinstance(comparable, Mapping):
        for source in comparable.get("sources") or []:
            if isinstance(source, Mapping):
                add(source.get("source_key") or source.get("key"))
    fp = justification.get("first_principles")
    if isinstance(fp, Mapping):
        for param in fp.get("parameters") or []:
            if isinstance(param, Mapping):
                add(param.get("source_key"))
    return keys


def _rubric_summary(justification: Mapping[str, object]) -> str:
    comparable = justification.get("comparable")
    if not isinstance(comparable, Mapping):
        return ""
    rubric = comparable.get("rubric")
    if not isinstance(rubric, Mapping):
        return ""
    parts: list[str] = []
    for dimension, item in rubric.items():
        score = item.get("score") if isinstance(item, Mapping) else item
        parts.append(f"{dimension}:{score}")
    return ", ".join(parts)


def _estimate_notes(row: Mapping[str, object]) -> str:
    justification = _parse_justification(row)
    method = str(justification.get("method") or "unknown")
    confidence = str(justification.get("estimator_confidence") or "")
    source_keys = ", ".join(_source_keys_from_justification(justification))
    caveats = justification.get("caveats")
    caveat_text = "; ".join(str(c) for c in caveats) if isinstance(caveats, list) else str(caveats or "")
    parts = [f"method={method}"]
    if confidence:
        parts.append(f"confidence={confidence}")
    rubric = _rubric_summary(justification)
    if rubric:
        parts.append(f"rubric={rubric}")
    if source_keys:
        parts.append(f"cited_source_keys={source_keys}")
    if caveat_text:
        parts.append(f"caveats={caveat_text}")
    if justification.get("failure_reason"):
        parts.append(f"failure_reason={justification.get('failure_reason')}")
    prior_notes = str(row.get("notes") or "").strip()
    if prior_notes:
        parts.append(prior_notes)
    return " | ".join(parts)


def _prior_answers(queue_path: str | Path) -> dict[tuple[str, str, str, str, str], dict[str, str]]:
    rows = read_rows(queue_path, required_columns=HELD_ESTIMATES_FIELDNAMES, missing_ok=True)
    answers: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if any((row.get(field) or "").strip() for field in ANSWER_FIELDS):
            answers[_estimate_key(row)] = {field: row.get(field, "") for field in ANSWER_FIELDS}
    return answers


def held_estimate_rows(
    *,
    audit_path: str | Path,
    sources_path: str | Path | None = "Sources.csv",
    prior_queue_path: str | Path | None = None,
) -> tuple[list[dict[str, str]], int]:
    audit_rows = read_rows(
        audit_path,
        required_columns=["entity", "parameter", "source_key", "quality_tag", "estimate_justification"],
        missing_ok=True,
    )
    prior = _prior_answers(prior_queue_path) if prior_queue_path else {}
    out: list[dict[str, str]] = []
    carried = 0
    for row in audit_rows:
        if str(row.get("quality_tag") or "").strip().upper() != ESTIMATE_QUALITY_TAG:
            continue
        if str(row.get("relevance_status") or "").strip().lower() == "reject":
            continue
        if str(row.get("held_estimate_status") or "").strip().lower() in RESOLVED_STATUSES:
            continue
        queue_row = {name: row.get(name, "") for name in HELD_ESTIMATES_FIELDNAMES}
        if sources_path is not None and queue_row.get("source_key") and not queue_row.get("source_url"):
            queue_row["source_url"] = source_url_for(queue_row["source_key"], sources_path)
        queue_row["notes"] = _estimate_notes(row)
        answer = prior.get(_estimate_key(queue_row))
        if answer:
            queue_row.update(answer)
            carried += 1
        out.append(queue_row)
    return out, carried


def sweep_held_estimates(
    *,
    audit_path: str | Path = "Audit.csv",
    output_path: str | Path = "held_estimates.csv",
    sources_path: str | Path | None = "Sources.csv",
    dry_run: bool = False,
) -> dict[str, object]:
    rows, carried = held_estimate_rows(
        audit_path=audit_path,
        sources_path=sources_path,
        prior_queue_path=output_path,
    )
    if not dry_run:
        write_rows(output_path, HELD_ESTIMATES_FIELDNAMES, rows)
    return {"rows": rows, "carried": carried, "output_path": Path(output_path), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, default=Path("Audit.csv"), help="Audit CSV to scan")
    parser.add_argument("--output", type=Path, default=Path("held_estimates.csv"), help="Queue CSV to write")
    parser.add_argument("--sources", type=Path, default=Path("Sources.csv"), help="Sources CSV for source_url fill")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args(argv)

    try:
        result = sweep_held_estimates(
            audit_path=args.audit,
            output_path=args.output,
            sources_path=args.sources,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, SourceUrlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{len(result['rows'])} held estimate row(s) -> {args.output} "
        f"({result['carried']} prior answer(s) preserved)"
    )
    if result["rows"]:
        print("Next: fill proposed_verdict and analyst_answer, then run apply_held_estimates.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
