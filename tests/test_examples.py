"""Tests for T10 worked examples."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_csvs import build  # noqa: E402
from lib.csvio import AUDIT_FIELDNAMES, read_rows, write_rows  # noqa: E402
from lib.schema import GLOBAL_ENTITY_ID, load_schema, validate_schema  # noqa: E402
from normalize import normalize_audit  # noqa: E402


EXAMPLES = ROOT / "examples"
FIXTURES = ROOT / "tests" / "fixtures"
TI_EXAMPLE = EXAMPLES / "ti-6al-4v"
COMPUTE_EXAMPLE = EXAMPLES / "compute-service"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def blank_audit_row(**updates):
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "source_key": "example-source",
            "source_url": "https://example.test/source",
            "page_ref": "p. 1",
            "quality_tag": "A",
            "relevance_status": "clear",
        }
    )
    row.update(updates)
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
        [{"from_unit": "kWh", "to_unit": "kWh", "factor": "1"}],
    )
    return conv


class WorkedExampleTests(unittest.TestCase):
    def test_t10_files_are_present(self):
        required = [
            TI_EXAMPLE / "scope.md",
            TI_EXAMPLE / "data-requirements.md",
            TI_EXAMPLE / "tea-schema.json",
            TI_EXAMPLE / "expected" / "Main Input.csv",
            COMPUTE_EXAMPLE / "scope.md",
            COMPUTE_EXAMPLE / "data-requirements.md",
            COMPUTE_EXAMPLE / "tea-schema.json",
        ]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
        self.assertEqual(missing, [])

    def test_example_configs_validate_cleanly(self):
        for path in (TI_EXAMPLE / "tea-schema.json", COMPUTE_EXAMPLE / "tea-schema.json"):
            with self.subTest(path=path):
                report = validate_schema(load_json(path))
                self.assertEqual(report.errors, [])
                self.assertEqual([str(q) for q in report.open_questions], [])
                self.assertEqual(report.warnings, [])

    def test_example_configs_match_validated_fixtures(self):
        pairs = [
            (TI_EXAMPLE / "tea-schema.json", FIXTURES / "ti-6al-4v.tea-schema.json"),
            (COMPUTE_EXAMPLE / "tea-schema.json", FIXTURES / "compute-service.tea-schema.json"),
        ]
        for example, fixture in pairs:
            with self.subTest(example=example):
                self.assertEqual(load_json(example), load_json(fixture))

    def test_ti_run2_oracle_is_present(self):
        oracle = TI_EXAMPLE / "expected" / "Main Input.csv"
        with open(oracle, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
            header = fh.seek(0) or next(csv.reader(fh))

        self.assertEqual(header[:2], ["unit", "field"])
        self.assertEqual(len(rows), 84)
        self.assertGreaterEqual(len({(row["unit"], row["field"]) for row in rows}), 71)

    def test_examples_build_skeletons(self):
        cases = [
            (TI_EXAMPLE / "tea-schema.json", 74, 3),
            (COMPUTE_EXAMPLE / "tea-schema.json", 17, 4),
        ]
        for schema_path, expected_rows, expected_ref_rows in cases:
            with self.subTest(schema=schema_path):
                schema = load_schema(schema_path)
                with tempfile.TemporaryDirectory() as tmp:
                    result = build(schema_path, output_dir=tmp)
                    rows = read_rows(Path(tmp) / "Main Input.csv")
                self.assertEqual(result["skeleton_rows"], expected_rows)
                self.assertEqual(len(rows), expected_rows)
                self.assertEqual(
                    len([cell for cell in schema.skeleton_cells() if cell[0] == GLOBAL_ENTITY_ID]),
                    expected_ref_rows,
                )

    def test_compute_example_smoke_normalizes_without_industrial_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            audit = tmp_path / "Audit.csv"
            output = tmp_path / "Audit_normalized.csv"
            conv = write_compute_conventions(tmp_path)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="monthly_cost",
                        raw_value="$1,000",
                        raw_units="USD/month",
                        raw_basis_year="2024",
                    )
                ],
            )

            normalize_audit(
                schema_path=COMPUTE_EXAMPLE / "tea-schema.json",
                audit_path=audit,
                output_path=output,
                conventions_dir=conv,
                sources_path=None,
            )

            row = read_rows(output)[0]
            self.assertEqual(row["normalized_value"], "1100")
            self.assertEqual(row["normalized_units"], "USD/month")
            self.assertIn("CPI 2024->2025", row["transform_steps"])
            self.assertNotIn("CEPCI", row["transform_steps"])


if __name__ == "__main__":
    unittest.main()

