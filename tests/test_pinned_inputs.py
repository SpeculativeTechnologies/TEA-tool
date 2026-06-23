"""Tests for T8 pinned inputs and finalization."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from consolidate import consolidate  # noqa: E402
from finalize_inputs import finalize_inputs  # noqa: E402
from lib.csvio import (  # noqa: E402
    AUDIT_FIELDNAMES,
    PINNED_INPUTS_FIELDNAMES,
    SOURCES_FIELDNAMES,
    read_rows,
    write_rows,
)
from load_pinned_inputs import load_pinned_inputs  # noqa: E402
from normalize import normalize_audit  # noqa: E402


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


def pinned_row(**updates):
    row = {name: "" for name in PINNED_INPUTS_FIELDNAMES}
    row.update(
        {
            "entity": "compute_hardware",
            "parameter": "monthly_cost",
            "raw_value": "100",
            "raw_units": "USD/month",
            "raw_basis_year": "2025",
            "source_key": "pinned-source",
            "source_url": "https://example.test/pinned",
            "page_ref": "Table 1",
            "quality_tag": "D",
            "notes": "Carry forward from system 1 comparison run.",
        }
    )
    row.update(updates)
    return row


class PinnedInputTests(unittest.TestCase):
    def test_loader_validates_and_marks_audit_plus_main_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_rows(root / "pinned-inputs.csv", PINNED_INPUTS_FIELDNAMES, [pinned_row()])

            result = load_pinned_inputs(schema_path=COMPUTE_SCHEMA, run_dir=root)

            self.assertEqual(result["pinned_rows"], 1)
            audit = read_rows(root / "Audit.csv")
            self.assertEqual(audit[0]["relevance_status"], "pinned")
            self.assertEqual(audit[0]["source_url"], "https://example.test/pinned")
            main = read_rows(root / "Main Input.csv")
            cell = [
                row for row in main
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(cell["pinned"], "TRUE")
            self.assertEqual(cell["raw_value"], "100")

    def test_loader_rejects_schema_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_rows(
                root / "pinned-inputs.csv",
                PINNED_INPUTS_FIELDNAMES,
                [pinned_row(parameter="industrial_electricity_price")],
            )
            with self.assertRaises(ValueError) as ctx:
                load_pinned_inputs(schema_path=COMPUTE_SCHEMA, run_dir=root)
            self.assertIn("does not apply", str(ctx.exception))

    def test_pinned_cell_normalizes_locks_and_finalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conv = write_conventions(root)
            write_rows(root / "pinned-inputs.csv", PINNED_INPUTS_FIELDNAMES, [pinned_row()])
            write_rows(root / "Sources.csv", SOURCES_FIELDNAMES, [])
            load_pinned_inputs(schema_path=COMPUTE_SCHEMA, run_dir=root)

            normalized = root / "Audit_normalized.csv"
            normalize_audit(
                schema_path=COMPUTE_SCHEMA,
                audit_path=root / "Audit.csv",
                output_path=normalized,
                conventions_dir=conv,
                sources_path=root / "Sources.csv",
            )
            consolidate(
                schema_path=COMPUTE_SCHEMA,
                audit_path=normalized,
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                scope_fit_decisions_path=None,
            )
            main_cell = [
                row for row in read_rows(root / "Main Input.csv")
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(main_cell["pinned"], "TRUE")
            self.assertEqual(main_cell["normalized_value"], "100")
            self.assertEqual(main_cell["source_key"], "pinned-source")

            final = root / "final"
            result = finalize_inputs(
                schema_path=COMPUTE_SCHEMA,
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                output_dir=final,
            )
            self.assertEqual(result["pinned"], 1)
            self.assertTrue((final / "Main Input.csv").exists())
            self.assertTrue((final / "Reference Values.csv").exists())
            manifest = (final / "run-manifest.md").read_text(encoding="utf-8")
            self.assertIn("Pinned Cells", manifest)
            self.assertIn("compute_hardware", manifest)


if __name__ == "__main__":
    unittest.main()
