"""Run a tiny live-source smoke TEA from setup through finalization.

This harness is intentionally small but phase-complete. It creates a fresh run
folder for an electric-kettle mini TEA, records source candidates found during
live web search, creates approved source snapshots, ingests extractor-shaped
JSON, auto-fills analyst review queues, runs normalization/consolidation, adds
one E-quality estimate, accepts it, and finalizes the inputs.

It is not a replacement for a real analyst run. Its purpose is to exercise the
same file contracts and human-gate scripts with a tiny amount of source data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Mapping, Sequence

from append_estimation_rows import append_estimation_rows
from apply_held_estimates import apply_held_estimates
from apply_held_verdicts import apply_verdicts
from apply_normalization_flags import apply_normalization_flags
from build_csvs import build
from build_estimation_manifest import build_manifest as build_estimation_manifest
from build_estimation_manifest import write_manifest as write_estimation_manifest
from consolidate import consolidate
from extraction_manifest import build_manifest as build_extraction_manifest
from extraction_manifest import write_manifest as write_extraction_manifest
from finalize_inputs import finalize_inputs
from ingest_extractor_output import ingest_extractor_output
from lib.csvio import (
    CSV_SCHEMAS,
    column_names,
    read_rows,
    write_rows,
)
from normalize import normalize_audit
from register_sources import register_sources
from rename_sources import rename_sources
from scaffold_conventions import scaffold_conventions
from sweep_held_estimates import sweep_held_estimates
from sweep_held_questions import sweep_held_questions
from sweep_normalization_flags import sweep_normalization_flags
from sweep_value_disagreements import sweep_value_disagreements


ROOT = Path(__file__).resolve().parent.parent


def _today() -> str:
    return dt.date.today().isoformat()


def _timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _write_json(path: Path, doc: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(doc), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _safe_fresh_run_dir(run_dir: Path, *, force: bool) -> None:
    resolved = run_dir.resolve()
    allowed_root = (ROOT / "runs").resolve()
    if run_dir.exists():
        if not force:
            raise FileExistsError(f"{run_dir} already exists; pass --force or choose another --run-dir")
        if allowed_root not in resolved.parents and resolved != allowed_root:
            raise ValueError(f"refusing to remove run dir outside {allowed_root}: {resolved}")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)


def write_stage0_inputs(run_dir: Path) -> Path:
    schema_path = run_dir / "tea-schema.json"
    _write_text(
        run_dir / "scope.md",
        """
        # Electric Kettle Smoke TEA

        Goal: prepare model-ready inputs for the tiny cost of boiling one liter
        of water in a household electric kettle.

        System boundary: one electric kettle activity, grid electricity only.
        The run stops at populated inputs and does not calculate the final cost.

        Functional unit: one liter of boiled water.
        Entity: `boil_water`, an electric kettle heating water to boiling.
        Geography/basis: US, USD, 2025.
        """,
    )
    _write_text(
        run_dir / "data-requirements.md",
        """
        # Data Requirements

        Entity `boil_water` needs a kettle power rating and an ideal thermal
        energy requirement per liter. A context-free US residential electricity
        price is carried under `REF`.

        The ideal heat energy row is deliberately left for Phase 6 estimation so
        the held-estimate gate is exercised.
        """,
    )
    _write_json(
        schema_path,
        {
            "schema_version": "1.0",
            "tea_id": "electric-kettle-smoke",
            "display_name": "Electric Kettle Smoke TEA",
            "vocabulary": {"entity": "activity", "parameter": "input"},
            "functional_unit": {"name": "one liter of boiled water", "symbol": "1 liter"},
            "basis": {
                "currency": "USD",
                "base_year": 2025,
                "inflation_index": "none",
                "geography": "US",
            },
            "quality_tags": ["A", "B", "C", "D", "E"],
            "entities": [
                {
                    "id": "boil_water",
                    "name": "Boil water in an electric kettle",
                    "output": "boiled water",
                    "description": "A household electric kettle heating water to boiling.",
                    "scope_frame": {
                        "in_scope": "Household electric kettle power and ideal energy to boil one liter of water.",
                        "known_out_of_scope": [
                            "stovetop kettle",
                            "industrial water heating",
                            "space-heating appliances",
                        ],
                    },
                    "estimation_policy": "first_principles_only",
                }
            ],
            "parameters": [
                {
                    "id": "power_rating",
                    "label": "Electric kettle power rating",
                    "rule_type": "RATE",
                    "units": "kW",
                    "applies_to": ["boil_water"],
                    "first_class": True,
                    "description": "Nominal electric-kettle power draw.",
                },
                {
                    "id": "ideal_heat_energy",
                    "label": "Ideal heat energy per liter",
                    "rule_type": "INTENSITY",
                    "numerator_units": "kWh",
                    "per": "functional_unit",
                    "applies_to": ["boil_water"],
                    "first_class": True,
                    "description": "First-principles sensible heat to raise one liter of water to boiling.",
                },
                {
                    "id": "electricity_price",
                    "label": "US residential electricity price",
                    "rule_type": "MONETARY",
                    "context_free": True,
                    "reference_value": True,
                    "scope": "global",
                    "canonical_unit": "USD/kWh",
                    "market_basis": "US average residential retail electricity",
                },
            ],
            "estimation": {},
            "conventions_needed": ["currency_rates", "unit_conversions"],
            "validation_targets": [
                {
                    "metric": "sanity check cost per liter",
                    "target": 0.02,
                    "unit": "USD/liter",
                    "source": "Derived by analyst outside this tool.",
                }
            ],
            "defaults": {"extraction_batch_size": 2},
        },
    )
    return schema_path


def write_search_artifacts(run_dir: Path) -> Path:
    search_dir = run_dir / "search-history"
    source_dir = run_dir / "master list sources"
    candidates_path = search_dir / "master-list.json"
    _write_json(
        candidates_path,
        {
            "search_notes": (
                "Live smoke run. Candidate URLs were selected from a minimal web search "
                "for kettle power rating and US residential electricity price."
            ),
            "reference_value_subqueries": [
                {
                    "parameter": "electricity_price",
                    "query": "US average residential electricity price cents per kilowatt-hour May 2025 EIA",
                }
            ],
            "candidates": [
                {
                    "source_key": "kettle-wikipedia",
                    "title": "Kettle",
                    "authors": "Wikipedia contributors",
                    "year": "2026",
                    "publisher_or_journal": "Wikipedia",
                    "source_url": "https://en.wikipedia.org/wiki/Kettle",
                    "doi": "",
                    "quality_estimate": "C",
                    "access_notes": "Open web source used only for a tiny smoke-test power-rating extraction.",
                    "field_coverage": [{"entity": "boil_water", "parameters": ["power_rating"]}],
                },
                {
                    "source_key": "axios-eia-electricity",
                    "title": "Electricity costs rise amid data center boom",
                    "authors": "Alex Fitzpatrick, Axios; citing U.S. Energy Information Administration",
                    "year": "2025",
                    "publisher_or_journal": "Axios",
                    "source_url": "https://www.axios.com/2025/08/04/electricity-costs-bills-data-centers-ai",
                    "doi": "",
                    "quality_estimate": "B",
                    "access_notes": "Used as a public citation for EIA-reported May 2025 average residential price.",
                    "field_coverage": [{"entity": "REF", "parameters": ["electricity_price"]}],
                },
            ],
        },
    )
    _write_text(
        source_dir / "raw-kettle-wikipedia.txt",
        """
        Source snapshot for kettle-wikipedia
        Title: Kettle
        URL: https://en.wikipedia.org/wiki/Kettle

        Electric kettles typically have a heating element with a power rating of
        2-3 kW. The same source also mentions current draw up to 13 A; that
        current figure is intentionally routed through review in this smoke run.
        """,
    )
    _write_text(
        source_dir / "raw-axios-eia-electricity.txt",
        """
        Source snapshot for axios-eia-electricity
        Title: Electricity costs rise amid data center boom
        URL: https://www.axios.com/2025/08/04/electricity-costs-bills-data-centers-ai

        The article reports that the nationwide average retail residential price
        for 1 kWh of electricity rose from 16.41 cents in May 2024 to 17.47
        cents in May 2025, citing the U.S. Energy Information Administration.
        The extractor records 17.47 cents/kWh as 0.1747 USD/kWh.
        """,
    )
    return candidates_path


def write_extractor_outputs(run_dir: Path) -> list[Path]:
    out_dir = run_dir / "extractions"
    kettle = out_dir / "kettle-wikipedia.extraction.json"
    electricity = out_dir / "axios-eia-electricity.extraction.json"
    _write_json(
        kettle,
        {
            "source_key": "kettle-wikipedia",
            "source_url": "https://en.wikipedia.org/wiki/Kettle",
            "extraction_summary": {"notes": "Smoke-test extraction from source snapshot."},
            "extracted_rows": [
                {
                    "entity": "boil_water",
                    "parameter": "power_rating",
                    "page_ref": "Electric kettles section",
                    "raw_value": "2-3",
                    "raw_units": "kW",
                    "quality_tag": "C",
                    "relevance_status": "clear",
                    "extractor_notes": "Source states electric kettle heating elements are typically rated 2-3 kW.",
                },
                {
                    "entity": "boil_water",
                    "parameter": "power_rating",
                    "page_ref": "Electric kettles section",
                    "raw_value": "13",
                    "raw_units": "A",
                    "quality_tag": "C",
                    "relevance_status": "hold",
                    "analyst_question": (
                        "The source reports current draw up to 13 A, not a kW power rating. "
                        "Keep it temporarily to verify the normalization-review gate?"
                    ),
                    "extractor_notes": "Deliberate hold row for automated analyst-gate smoke coverage.",
                },
            ],
        },
    )
    _write_json(
        electricity,
        {
            "source_key": "axios-eia-electricity",
            "source_url": "https://www.axios.com/2025/08/04/electricity-costs-bills-data-centers-ai",
            "extraction_summary": {"notes": "Context-free reference-value extraction."},
            "extracted_rows": [
                {
                    "entity": "REF",
                    "parameter": "electricity_price",
                    "page_ref": "By the numbers",
                    "raw_value": "0.1747",
                    "raw_units": "USD/kWh",
                    "raw_basis_year": "2025",
                    "quality_tag": "B",
                    "relevance_status": "clear",
                    "extractor_notes": "Source reports 17.47 cents/kWh for May 2025; recorded as 0.1747 USD/kWh.",
                }
            ],
        },
    )
    return [kettle, electricity]


def write_estimation_output(run_dir: Path) -> Path:
    path = run_dir / "estimation_output.json"
    _write_json(
        path,
        {
            "schema_tea_id": "electric-kettle-smoke",
            "force_refresh": False,
            "rows": [
                {
                    "entity": "boil_water",
                    "parameter": "ideal_heat_energy",
                    "source_key": "specific-heat-wiki",
                    "page_ref": "Water liquid specific heat row plus analyst calculation",
                    "raw_value": "0.093",
                    "raw_units": "kWh/liter",
                    "quality_tag": "E",
                    "relevance_status": "clear",
                    "estimate_justification": {
                        "method": "first_principles",
                        "estimator_confidence": "medium",
                        "cited_sources": [
                            {
                                "source_key": "specific-heat-wiki",
                                "authors": "Wikipedia contributors",
                                "title": "Table of specific heat capacities",
                                "year": "2026",
                                "publisher_or_journal": "Wikipedia",
                                "source_url": "https://en.wikipedia.org/wiki/Table_of_specific_heat_capacities",
                                "page_or_table_reference": "Water at 25 C, liquid",
                            }
                        ],
                        "comparable": None,
                        "first_principles": {
                            "equations": ["Q = m * c_p * delta_T", "kWh = kJ / 3600"],
                            "parameters": [
                                {
                                    "name": "water_mass",
                                    "value": "1",
                                    "units": "kg per liter",
                                    "source": "density approximation for smoke test",
                                },
                                {
                                    "name": "specific_heat_capacity",
                                    "value": "4.181",
                                    "units": "kJ/kg/K",
                                    "source_key": "specific-heat-wiki",
                                },
                                {
                                    "name": "temperature_rise",
                                    "value": "80",
                                    "units": "K",
                                    "source": "assumed 20 C to 100 C smoke-test basis",
                                },
                            ],
                            "derivation_steps": [
                                "1 kg * 4.181 kJ/kg/K * 80 K = 334.48 kJ",
                                "334.48 kJ / 3600 = 0.0929 kWh",
                                "Rounded to 0.093 kWh per liter.",
                            ],
                        },
                        "caveats": ["Ideal sensible heat only; excludes kettle losses and evaporation."],
                    },
                    "notes": "Phase 6 smoke estimate; reviewed automatically by this harness.",
                }
            ],
        },
    )
    return path


def fill_queue(
    path: Path,
    fieldnames: Sequence[str],
    updates: Mapping[str, str],
) -> int:
    rows = read_rows(path, required_columns=fieldnames, missing_ok=True)
    for row in rows:
        row.update(updates)
    write_rows(path, fieldnames, rows)
    return len(rows)


def run_live_smoke(run_dir: Path, *, force: bool = False) -> dict[str, object]:
    run_dir = run_dir if run_dir.is_absolute() else ROOT / run_dir
    _safe_fresh_run_dir(run_dir, force=force)

    schema_path = write_stage0_inputs(run_dir)
    build(schema_path, output_dir=run_dir, force=True)
    scaffold_conventions(schema_path=schema_path, output_dir=run_dir / "conventions", force=True)

    candidates_path = write_search_artifacts(run_dir)
    source_dir = run_dir / "master list sources"
    rename_result = rename_sources(
        schema_path=schema_path,
        input_path=candidates_path,
        source_dir=source_dir,
        apply=True,
        min_score=1,
    )
    registered = register_sources(
        schema_path=schema_path,
        input_path=candidates_path,
        source_dir=source_dir,
        sources_path=run_dir / "Sources.csv",
        access_date=_today(),
    )

    extraction_manifest = build_extraction_manifest(
        schema_path=schema_path,
        inputs=[candidates_path],
        sources_path=run_dir / "Sources.csv",
        source_dirs=[source_dir],
        output_dir=run_dir / "extractions",
        main_input_path=run_dir / "Main Input.csv",
        audit_path=run_dir / "Audit.csv",
    )
    write_extraction_manifest(run_dir / "extractions" / "extraction_manifest.json", extraction_manifest)

    extractor_outputs = write_extractor_outputs(run_dir)
    ingest_counts = []
    for output in extractor_outputs:
        result = ingest_extractor_output(
            schema_path=schema_path,
            input_path=output,
            audit_path=run_dir / "Audit.csv",
            sources_path=run_dir / "Sources.csv",
        )
        ingest_counts.append(result["counts"])

    held_questions_path = run_dir / "held_questions.csv"
    held = sweep_held_questions(audit_path=run_dir / "Audit.csv", output_path=held_questions_path)
    held_answered = fill_queue(
        held_questions_path,
        column_names(CSV_SCHEMAS["held_questions.csv"]),
        {
            "proposed_verdict": "accept",
            "analyst_answer": "Accepted only to exercise normalization review; current draw is not a model-ready power rating.",
        },
    )
    held_applied = apply_verdicts(
        audit_path=run_dir / "Audit.csv",
        queue_path=held_questions_path,
        reextract_todo_path=run_dir / "reextract_todo.csv",
    )

    normalized = normalize_audit(
        schema_path=schema_path,
        audit_path=run_dir / "Audit.csv",
        output_path=run_dir / "Audit_normalized.csv",
        conventions_dir=run_dir / "conventions",
        sources_path=run_dir / "Sources.csv",
    )
    flags_path = run_dir / "normalization_flags.csv"
    flags = sweep_normalization_flags(
        audit_path=run_dir / "Audit_normalized.csv",
        output_path=flags_path,
    )
    flags_answered = fill_queue(
        flags_path,
        column_names(CSV_SCHEMAS["normalization_flags.csv"]),
        {
            "proposed_action": "reject",
            "analyst_answer": "Current in amperes cannot be converted to kW without additional voltage/power-factor assumptions.",
        },
    )
    flags_applied = apply_normalization_flags(
        audit_path=run_dir / "Audit_normalized.csv",
        queue_path=flags_path,
    )

    disagreements_path = run_dir / "value_disagreements.csv"
    disagreements = sweep_value_disagreements(
        schema_path=schema_path,
        audit_path=run_dir / "Audit_normalized.csv",
        output_path=disagreements_path,
        sources_path=run_dir / "Sources.csv",
    )
    first_consolidation = consolidate(
        schema_path=schema_path,
        audit_path=run_dir / "Audit_normalized.csv",
        main_input_path=run_dir / "Main Input.csv",
        audit_output_path=run_dir / "Audit_normalized_consolidated.csv",
        sources_path=run_dir / "Sources.csv",
        scope_fit_decisions_path=None,
    )

    estimation_manifest = build_estimation_manifest(
        schema_path=schema_path,
        audit_path=run_dir / "Audit_normalized_consolidated.csv",
        main_input_path=run_dir / "Main Input.csv",
    )
    write_estimation_manifest(run_dir / "estimation_manifest.json", estimation_manifest)

    estimation_output = write_estimation_output(run_dir)
    appended_estimates = append_estimation_rows(
        schema_path=schema_path,
        input_path=estimation_output,
        audit_path=run_dir / "Audit_normalized_consolidated.csv",
        sources_path=run_dir / "Sources.csv",
    )
    held_estimates_path = run_dir / "held_estimates.csv"
    held_estimates = sweep_held_estimates(
        audit_path=run_dir / "Audit_normalized_consolidated.csv",
        output_path=held_estimates_path,
        sources_path=run_dir / "Sources.csv",
    )
    held_estimates_answered = fill_queue(
        held_estimates_path,
        column_names(CSV_SCHEMAS["held_estimates.csv"]),
        {
            "proposed_verdict": "accept",
            "analyst_answer": "Accepted for smoke test; estimate is transparent and correctly caveated.",
        },
    )
    held_estimates_applied = apply_held_estimates(
        audit_path=run_dir / "Audit_normalized_consolidated.csv",
        queue_path=held_estimates_path,
    )

    post_estimation_normalized = normalize_audit(
        schema_path=schema_path,
        audit_path=run_dir / "Audit_normalized_consolidated.csv",
        output_path=run_dir / "Audit_post_estimation_normalized.csv",
        conventions_dir=run_dir / "conventions",
        sources_path=run_dir / "Sources.csv",
        only_quality_tag="E",
    )
    final_consolidation = consolidate(
        schema_path=schema_path,
        audit_path=run_dir / "Audit_post_estimation_normalized.csv",
        main_input_path=run_dir / "Main Input.csv",
        audit_output_path=run_dir / "Audit_final_consolidated.csv",
        sources_path=run_dir / "Sources.csv",
        scope_fit_decisions_path=None,
    )
    final = finalize_inputs(
        schema_path=schema_path,
        main_input_path=run_dir / "Main Input.csv",
        sources_path=run_dir / "Sources.csv",
        output_dir=run_dir / "final",
    )

    summary = {
        "run_dir": str(run_dir),
        "registered_sources": len(registered["rows"]),
        "renamed_sources": len(rename_result["selected"]),
        "extraction_slices": extraction_manifest["count"],
        "ingest_counts": ingest_counts,
        "held_questions": len(held["rows"]),
        "held_questions_answered": held_answered,
        "held_question_apply_counts": held_applied["counts"],
        "normalization_counts": normalized["counts"],
        "normalization_flags": len(flags["rows"]),
        "normalization_flags_answered": flags_answered,
        "normalization_flag_apply_counts": flags_applied["counts"],
        "value_disagreements": len(disagreements["rows"]),
        "first_consolidation": first_consolidation,
        "estimation_manifest_counts": estimation_manifest["counts"],
        "estimate_rows_appended": len(appended_estimates["rows_appended"]),
        "held_estimates": len(held_estimates["rows"]),
        "held_estimates_answered": held_estimates_answered,
        "held_estimate_apply_counts": held_estimates_applied["counts"],
        "post_estimation_normalization_counts": post_estimation_normalized["counts"],
        "final_consolidation": final_consolidation,
        "final": {
            "filled": final["filled"],
            "main_rows": final["main_rows"],
            "gaps": final["gaps"],
            "reference_rows": final["reference_rows"],
            "manifest_path": str(final["manifest_path"]),
        },
    }
    _write_json(run_dir / "live-smoke-summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("runs") / f"live-smoke-kettle-{_timestamp()}",
        help="Run directory to create. Defaults to runs/live-smoke-kettle-<timestamp>.",
    )
    parser.add_argument("--force", action="store_true", help="Replace the run directory if it exists.")
    args = parser.parse_args(argv)

    try:
        summary = run_live_smoke(args.run_dir, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(_jsonable(summary), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
