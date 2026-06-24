"""End-to-end fixture tests for T11.

These tests wire the deterministic stages together around seeded rows. The
LLM search/extract/estimate work is intentionally represented by fixture CSVs;
the purpose here is to catch contract drift between build, normalize,
consolidate, and finalize.
"""

import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_csvs import build  # noqa: E402
from consolidate import consolidate  # noqa: E402
from finalize_inputs import finalize_inputs  # noqa: E402
from lib.csvio import AUDIT_FIELDNAMES, SOURCES_FIELDNAMES, read_rows, write_rows  # noqa: E402
from lib.schema import GLOBAL_ENTITY_ID, load_schema  # noqa: E402
from normalize import normalize_audit  # noqa: E402


EXAMPLES = ROOT / "examples"
TI_EXAMPLE = EXAMPLES / "ti-6al-4v"
COMPUTE_EXAMPLE = EXAMPLES / "compute-service"

TI_STRUCTURAL_DELTAS = {
    "missing_in_legacy_oracle": {
        ("1A", "consumables.cl2_makeup"),
        ("1B", "consumables.argon"),
        ("5", "consumables.argon"),
        (GLOBAL_ENTITY_ID, "al_v_master_alloy_price"),
        (GLOBAL_ENTITY_ID, "electricity_price"),
        (GLOBAL_ENTITY_ID, "natural_gas_price"),
    },
    "legacy_extras": {
        ("", "\u2014 Consumables \u2014"),
        ("1B", "consumables.mg_makeup"),
        ("2A", "consumables.lime"),
        ("2A", "consumables.naoh"),
        ("2B", "consumables.alf3"),
        ("2B", "consumables.carbon_anodes"),
        ("3", "V_yield"),
        ("3", "electricity"),
        ("3", "feedstock_quantity"),
        ("3", "output_notes"),
        ("3", "scaling_exponent"),
        ("3", "stoichiometry"),
        ("3", "thermal_energy"),
        ("4", "stoichiometry"),
        ("5", "stoichiometry"),
        ("6", "stoichiometry"),
        # The numeric-only contract dropped the JSON `stoichiometry` and TEXT
        # `output_notes` parameters; their oracle-covered cells are now extras.
        ("1A", "stoichiometry"),
        ("1B", "stoichiometry"),
        ("1C", "stoichiometry"),
        ("2A", "stoichiometry"),
        ("2B", "stoichiometry"),
        ("1A", "output_notes"),
        ("1B", "output_notes"),
        ("1C", "output_notes"),
        ("2A", "output_notes"),
        ("2B", "output_notes"),
        ("4", "output_notes"),
        ("5", "output_notes"),
        ("6", "output_notes"),
    },
}


def blank_audit_row(**updates):
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "page_ref": "fixture",
            "quality_tag": "A",
            "relevance_status": "clear",
        }
    )
    row.update(updates)
    if row.get("quality_tag") == "E" and row.get("normalized_value"):
        row["held_estimate_status"] = row.get("held_estimate_status") or "accept"
    if row.get("quality_tag") == "E" and row.get("capex_usd"):
        row["held_estimate_status"] = row.get("held_estimate_status") or "accept"
    return row


def write_compute_conventions(root: Path) -> Path:
    conv = root / "conventions"
    conv.mkdir()
    write_rows(
        conv / "currency-rates.csv",
        ["from_currency", "to_currency", "year", "rate", "source_note"],
        [{"from_currency": "USD", "to_currency": "USD", "year": "2024", "rate": "1"}],
    )
    write_rows(
        conv / "cpi.csv",
        ["year", "index", "source_note"],
        [{"year": "2024", "index": "100"}, {"year": "2025", "index": "110"}],
    )
    write_rows(
        conv / "unit-conversions.csv",
        ["from_unit", "to_unit", "factor", "note"],
        [
            {"from_unit": "kWh", "to_unit": "kWh", "factor": "1"},
            {"from_unit": "1M tokens/hour", "to_unit": "1M tokens/h", "factor": "1"},
        ],
    )
    return conv


def read_legacy_ti_oracle() -> list[dict[str, str]]:
    with open(TI_EXAMPLE / "expected" / "Main Input.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def legacy_to_audit_row(row: dict[str, str]) -> dict[str, str]:
    mapped = blank_audit_row(
        entity=row["unit"],
        parameter=row["field"],
        source_key=row["source_key"],
        source_url="",
        page_ref=row["page_ref"],
        raw_value=row["raw_value"],
        raw_units=row["raw_units"],
        raw_basis_scale=row["raw_basis_scale"],
        raw_basis_scale_units=row["raw_basis_scale_units"],
        raw_basis_year=row["raw_basis_year"],
        quality_tag=row["quality_tag"],
        normalized_value=row["normalized_value"],
        normalized_units=row["normalized_units"],
        capex_usd=row["capex_usd"],
        capex_form=row["capex_form"],
        capex_basis_year=row["capex_basis_year"],
        capex_basis_scale=row.get("capex_basis_scale_tpy", ""),
        capex_notes=row["capex_notes"],
        review_value=row["review_value"],
        review_units=row["review_units"],
        review_steps=row["review_steps"],
        cross_check_delta=row["cross_check_delta"],
        estimate_justification=row["estimate_justification"],
        notes=row["notes"],
    )
    if row["quality_tag"] == "E" and (row["normalized_value"] or row["capex_usd"]):
        mapped["held_estimate_status"] = "accept"
    return mapped


def project_ti_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "raw_value": row.get("raw_value", ""),
        "raw_units": row.get("raw_units", ""),
        "raw_basis_year": row.get("raw_basis_year", ""),
        "normalized_value": row.get("normalized_value", ""),
        "normalized_units": row.get("normalized_units", ""),
        "capex_usd": row.get("capex_usd", ""),
        "capex_form": row.get("capex_form", ""),
        "capex_basis_year": row.get("capex_basis_year", ""),
        "capex_notes": row.get("capex_notes", ""),
        "review_value": row.get("review_value", ""),
        "review_units": row.get("review_units", ""),
        "review_steps": row.get("review_steps", ""),
        "quality_tag": row.get("quality_tag", ""),
        "source_key": row.get("source_key", ""),
        "page_ref": row.get("page_ref", ""),
        "estimate_justification": row.get("estimate_justification", ""),
    }


class EndToEndFixtureTests(unittest.TestCase):
    def test_compute_build_normalize_consolidate_finalize_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_path = COMPUTE_EXAMPLE / "tea-schema.json"
            build(schema_path, output_dir=root)
            conv = write_compute_conventions(root)
            write_rows(
                root / "Sources.csv",
                SOURCES_FIELDNAMES,
                [
                    {
                        "source_key": "compute-benchmark",
                        "title": "Compute benchmark",
                        "year": "2024",
                        "source_url": "https://example.test/compute",
                        "source_role": "extraction",
                    }
                ],
            )
            write_rows(
                root / "Audit.csv",
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="monthly_cost",
                        source_key="compute-benchmark",
                        source_url="",
                        raw_value="$1000",
                        raw_units="USD/month",
                        raw_basis_year="2024",
                    ),
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="throughput",
                        source_key="compute-benchmark",
                        raw_value="2",
                        raw_units="1M tokens/hour",
                    ),
                ],
            )

            normalize_audit(
                schema_path=schema_path,
                audit_path=root / "Audit.csv",
                output_path=root / "Audit_normalized.csv",
                conventions_dir=conv,
                sources_path=root / "Sources.csv",
            )
            consolidated = consolidate(
                schema_path=schema_path,
                audit_path=root / "Audit_normalized.csv",
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                scope_fit_decisions_path=None,
            )
            self.assertEqual(consolidated["main_skeleton_rows"], 12)
            self.assertEqual(consolidated["main_filled"], 2)

            final = root / "final"
            # This drift test intentionally leaves cells unfilled; allow gaps so it
            # exercises build/normalize/consolidate/finalize without the no-gap gate.
            finalized = finalize_inputs(
                schema_path=schema_path,
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                output_dir=final,
                require_complete=False,
            )
            self.assertEqual(finalized["reference_rows"], 4)
            self.assertEqual(finalized["filled"], 2)
            main_rows = read_rows(final / "Main Input.csv")
            monthly_cost = [
                row for row in main_rows
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(monthly_cost["normalized_value"], "1100")
            self.assertEqual(monthly_cost["source_url"], "https://example.test/compute")
            manifest = (final / "run-manifest.md").read_text(encoding="utf-8")
            self.assertIn("Coverage: 2/12 filled; 10 residual gap(s)", manifest)
            self.assertNotIn("CEPCI", monthly_cost["notes"])

    def test_ti_legacy_oracle_regression_projection(self):
        schema = load_schema(TI_EXAMPLE / "tea-schema.json")
        oracle_rows = read_legacy_ti_oracle()
        oracle_by_cell = {(row["unit"], row["field"]): row for row in oracle_rows}
        skeleton = set(schema.skeleton_cells())

        self.assertEqual(set(skeleton - set(oracle_by_cell)), TI_STRUCTURAL_DELTAS["missing_in_legacy_oracle"])
        self.assertEqual(set(oracle_by_cell) - skeleton, TI_STRUCTURAL_DELTAS["legacy_extras"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_path = root / "tea-schema.json"
            shutil.copyfile(TI_EXAMPLE / "tea-schema.json", schema_path)
            build(schema_path, output_dir=root)
            common_rows = [
                legacy_to_audit_row(row)
                for cell, row in oracle_by_cell.items()
                if cell in skeleton
            ]
            write_rows(root / "Audit_normalized.csv", AUDIT_FIELDNAMES, common_rows)
            result = consolidate(
                schema_path=schema_path,
                audit_path=root / "Audit_normalized.csv",
                main_input_path=root / "Main Input.csv",
                sources_path=None,
                scope_fit_decisions_path=None,
            )
            self.assertEqual(result["selected"], len(common_rows))
            self.assertEqual(result["main_skeleton_rows"], 61)
            self.assertEqual(result["main_filled"], len(common_rows))

            main_by_cell = {
                (row["entity"], row["parameter"]): row
                for row in read_rows(root / "Main Input.csv")
            }
            for cell in sorted(skeleton & set(oracle_by_cell)):
                with self.subTest(cell=cell):
                    self.assertEqual(project_ti_row(main_by_cell[cell]), project_ti_row(oracle_by_cell[cell]))

            # The legacy oracle does not cover 6 schema cells; allow gaps here.
            finalized = finalize_inputs(
                schema_path=schema_path,
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                output_dir=root / "final",
                require_complete=False,
            )
            self.assertEqual(finalized["main_rows"], 61)
            self.assertEqual(finalized["filled"], len(common_rows))
            self.assertEqual(finalized["reference_rows"], 3)


if __name__ == "__main__":
    unittest.main()
