"""Tests for comparison shared inputs and finalization."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_csvs import build  # noqa: E402
from consolidate import consolidate  # noqa: E402
from finalize_comparison import finalize_comparison  # noqa: E402
from finalize_inputs import finalize_inputs  # noqa: E402
from lib.csvio import (  # noqa: E402
    SHARED_INPUTS_FIELDNAMES,
    SHARED_INPUT_MAPPINGS_FIELDNAMES,
    SOURCES_FIELDNAMES,
    read_rows,
    write_rows,
)
from materialize_shared_inputs import materialize_shared_inputs  # noqa: E402
from normalize import normalize_audit  # noqa: E402
from validate_comparison_project import ComparisonProjectError, load_project  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"


def write_conventions(root: Path) -> Path:
    conv = root / "conventions"
    conv.mkdir()
    write_rows(
        conv / "currency-rates.csv",
        ["from_currency", "to_currency", "year", "rate", "source_note"],
        [{"from_currency": "USD", "to_currency": "USD", "year": "2025", "rate": "1"}],
    )
    write_rows(
        conv / "unit-conversions.csv",
        ["from_unit", "to_unit", "factor", "note"],
        [{"from_unit": "USD/month", "to_unit": "USD/month", "factor": "1"}],
    )
    write_rows(
        conv / "cpi.csv",
        ["year", "index", "source_note"],
        [{"year": "2025", "index": "100"}],
    )
    return conv


def write_project(root: Path, *, bad_basis: bool = False, bad_mapping: bool = False) -> Path:
    option_dir = root / "options" / "incumbent"
    option_dir.mkdir(parents=True)
    schema_path = option_dir / "tea-schema.json"
    shutil.copyfile(COMPUTE_SCHEMA, schema_path)
    if bad_basis:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        data["basis"]["base_year"] = 2024
        schema_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    frame = {
        "comparison_id": "compute-comparison",
        "display_name": "Compute Comparison",
        "functional_unit": {"name": "1M tokens served", "symbol": "1M tokens"},
        "basis": {
            "currency": "USD",
            "base_year": 2025,
            "inflation_index": "CPI",
            "geography": "US",
        },
        "headline_metrics": ["monthly_cost"],
        "options": [
            {
                "option_id": "incumbent",
                "display_name": "Incumbent",
                "run_dir": "options/incumbent",
                "schema_path": "options/incumbent/tea-schema.json",
            }
        ],
    }
    (root / "comparison-frame.json").write_text(json.dumps(frame, indent=2), encoding="utf-8")
    write_rows(
        root / "shared-sources.csv",
        SOURCES_FIELDNAMES,
        [
            {
                "source_key": "shared-source",
                "title": "Shared source",
                "year": "2025",
                "source_url": "https://example.test/shared",
                "source_role": "extraction",
            }
        ],
    )
    write_rows(
        root / "shared-inputs.csv",
        SHARED_INPUTS_FIELDNAMES,
        [
            {
                "shared_input_id": "shared-monthly-cost",
                "raw_value": "100",
                "raw_units": "USD/month",
                "raw_basis_year": "2025",
                "source_key": "shared-source",
                "page_ref": "Table 1",
                "quality_tag": "D",
                "notes": "Reusable benchmark.",
            }
        ],
    )
    write_rows(
        root / "shared-input-mappings.csv",
        SHARED_INPUT_MAPPINGS_FIELDNAMES,
        [
            {
                "shared_input_id": "shared-monthly-cost",
                "option_id": "incumbent",
                "entity": "compute_hardware",
                "parameter": "missing_parameter" if bad_mapping else "monthly_cost",
                "notes": "Apply to compute hardware.",
            }
        ],
    )
    return option_dir


class SharedInputTests(unittest.TestCase):
    def test_validation_materialization_and_idempotent_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            option_dir = write_project(root)
            build(option_dir / "tea-schema.json", output_dir=option_dir)

            project = load_project(root)
            self.assertEqual(len(project.options), 1)
            result = materialize_shared_inputs(project_dir=root)
            self.assertEqual(result["options"]["incumbent"]["shared_rows"], 1)
            materialize_shared_inputs(project_dir=root)

            audit = read_rows(option_dir / "Audit.csv")
            shared_rows = [row for row in audit if row["input_origin"] == "shared"]
            self.assertEqual(len(shared_rows), 1)
            self.assertEqual(shared_rows[0]["relevance_status"], "clear")
            self.assertEqual(shared_rows[0]["source_url"], "https://example.test/shared")
            main = read_rows(option_dir / "Main Input.csv")
            cell = [
                row for row in main
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(cell["input_origin"], "shared")
            self.assertEqual(cell["raw_value"], "100")

    def test_validation_rejects_basis_and_mapping_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, bad_basis=True)
            with self.assertRaises(ComparisonProjectError) as ctx:
                load_project(root)
            self.assertIn("basis.base_year", str(ctx.exception))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, bad_mapping=True)
            with self.assertRaises(ComparisonProjectError) as ctx:
                load_project(root)
            self.assertIn("unknown parameter", str(ctx.exception))

    def test_shared_inputs_cannot_prepopulate_estimates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            rows = read_rows(root / "shared-inputs.csv")
            rows[0]["quality_tag"] = "E"
            write_rows(root / "shared-inputs.csv", SHARED_INPUTS_FIELDNAMES, rows)
            with self.assertRaisesRegex(ComparisonProjectError, "Phase 6 estimation"):
                load_project(root)

    def test_shared_cell_normalizes_selects_and_finalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            option_dir = write_project(root)
            build(option_dir / "tea-schema.json", output_dir=option_dir)
            conv = write_conventions(option_dir)
            materialize_shared_inputs(project_dir=root)

            normalize_audit(
                schema_path=option_dir / "tea-schema.json",
                audit_path=option_dir / "Audit.csv",
                output_path=option_dir / "Audit_normalized.csv",
                conventions_dir=conv,
                sources_path=option_dir / "Sources.csv",
            )
            consolidate(
                schema_path=option_dir / "tea-schema.json",
                audit_path=option_dir / "Audit_normalized.csv",
                main_input_path=option_dir / "Main Input.csv",
                sources_path=option_dir / "Sources.csv",
                scope_fit_decisions_path=None,
            )
            main_cell = [
                row for row in read_rows(option_dir / "Main Input.csv")
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(main_cell["input_origin"], "shared")
            self.assertEqual(main_cell["normalized_value"], "100")

            finalize_inputs(
                schema_path=option_dir / "tea-schema.json",
                main_input_path=option_dir / "Main Input.csv",
                sources_path=option_dir / "Sources.csv",
                output_dir=option_dir / "final",
                require_complete=False,
            )
            manifest = (option_dir / "final" / "run-manifest.md").read_text(encoding="utf-8")
            self.assertIn("Shared Inputs", manifest)

            result = finalize_comparison(project_dir=root)
            self.assertEqual(result["shared_rows"], 1)
            self.assertTrue((root / "final" / "shared-assumptions.csv").exists())
            self.assertTrue((root / "final" / "comparison-manifest.md").exists())


if __name__ == "__main__":
    unittest.main()
