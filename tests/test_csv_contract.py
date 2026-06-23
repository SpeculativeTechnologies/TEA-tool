"""Tests for T2 CSV contracts, builder, and source_url helper."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_csvs import build, main_input_skeleton_rows  # noqa: E402
from lib.csvio import (  # noqa: E402
    AUDIT_FIELDNAMES,
    CSV_SCHEMAS,
    MAIN_INPUT_FIELDNAMES,
    PINNED_INPUTS_FIELDNAMES,
    SOURCES_FIELDNAMES,
    append_rows,
    column_names,
    read_header,
    read_rows,
    write_rows,
)
from lib.schema import GLOBAL_ENTITY_ID, load_schema  # noqa: E402
from lib.source_url import SourceUrlError, source_url_for  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
TI_SCHEMA = FIXTURES / "ti-6al-4v.tea-schema.json"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"


class CsvSchemaTests(unittest.TestCase):
    def test_sources_uses_source_url_and_role_flag(self):
        self.assertIn("source_url", SOURCES_FIELDNAMES)
        self.assertIn("source_role", SOURCES_FIELDNAMES)
        self.assertNotIn("url_or_doi", SOURCES_FIELDNAMES)

    def test_audit_and_main_use_neutral_vocabulary(self):
        self.assertEqual(AUDIT_FIELDNAMES[:2], ["entity", "parameter"])
        self.assertEqual(MAIN_INPUT_FIELDNAMES[:2], ["entity", "parameter"])
        self.assertNotIn("unit", AUDIT_FIELDNAMES)
        self.assertNotIn("field", AUDIT_FIELDNAMES)
        self.assertNotIn("unit", MAIN_INPUT_FIELDNAMES)
        self.assertNotIn("field", MAIN_INPUT_FIELDNAMES)

    def test_every_source_key_bearing_schema_has_source_url(self):
        for name, schema in CSV_SCHEMAS.items():
            fields = column_names(schema)
            if "source_key" in fields:
                self.assertIn("source_url", fields, name)

    def test_capex_scale_columns_are_domain_neutral(self):
        self.assertIn("capex_basis_scale", AUDIT_FIELDNAMES)
        self.assertIn("capex_basis_scale_units", AUDIT_FIELDNAMES)
        self.assertNotIn("capex_basis_scale_tpy", AUDIT_FIELDNAMES)


class CsvIoTests(unittest.TestCase):
    def test_write_and_read_rows_use_stable_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            write_rows(path, ["b", "a", "c"], [{"a": 1, "c": None}])
            self.assertEqual(read_header(path), ["b", "a", "c"])
            self.assertEqual(read_rows(path), [{"b": "", "a": "1", "c": ""}])

    def test_write_rows_rejects_unknown_columns_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_rows(Path(tmp) / "bad.csv", ["a"], [{"a": "ok", "b": "no"}])

    def test_append_rows_creates_header_then_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            append_rows(path, ["a", "b"], [{"a": "one"}])
            append_rows(path, ["a", "b"], [{"b": "two"}])
            self.assertEqual(read_rows(path), [{"a": "one", "b": ""}, {"a": "", "b": "two"}])


class SourceUrlTests(unittest.TestCase):
    def test_source_url_for_denormalizes_from_sources_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp) / "Sources.csv"
            write_rows(
                sources,
                SOURCES_FIELDNAMES,
                [
                    {
                        "source_key": "doe-report",
                        "title": "DOE report",
                        "source_url": "https://example.test/doe",
                        "source_role": "extraction",
                    }
                ],
            )
            self.assertEqual(source_url_for("doe-report", sources), "https://example.test/doe")
            self.assertEqual(source_url_for("missing", sources), "")
            with self.assertRaises(SourceUrlError):
                source_url_for("missing", sources, required=True)

    def test_conflicting_duplicate_source_urls_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp) / "Sources.csv"
            write_rows(
                sources,
                SOURCES_FIELDNAMES,
                [
                    {"source_key": "dup", "source_url": "https://one.test"},
                    {"source_key": "dup", "source_url": "https://two.test"},
                ],
            )
            with self.assertRaises(SourceUrlError):
                source_url_for("dup", sources)


class BuildCsvsTests(unittest.TestCase):
    def test_ti_builds_run2_entity_skeleton_plus_reference_rows(self):
        schema = load_schema(TI_SCHEMA)
        self.assertEqual(len([c for c in schema.skeleton_cells() if c[0] != GLOBAL_ENTITY_ID]), 71)
        self.assertEqual(len([c for c in schema.skeleton_cells() if c[0] == GLOBAL_ENTITY_ID]), 3)

        with tempfile.TemporaryDirectory() as tmp:
            result = build(TI_SCHEMA, output_dir=tmp)
            out = Path(tmp)

            self.assertEqual(result["skeleton_rows"], 74)
            self.assertEqual(read_header(out / "Audit.csv"), AUDIT_FIELDNAMES)
            self.assertEqual(read_rows(out / "Audit.csv"), [])
            self.assertEqual(read_header(out / "Sources.csv"), SOURCES_FIELDNAMES)
            self.assertEqual(read_rows(out / "Sources.csv"), [])
            self.assertEqual(read_header(out / "Main Input.csv"), MAIN_INPUT_FIELDNAMES)

            rows = read_rows(out / "Main Input.csv")
            self.assertEqual(len(rows), 74)
            cellset = {(row["entity"], row["parameter"]) for row in rows}
            self.assertEqual(cellset, set(schema.skeleton_cells()))
            self.assertIn((GLOBAL_ENTITY_ID, "electricity_price"), cellset)
            self.assertNotIn(("1A", "electricity_price"), cellset)
            self.assertIn(("1C", "Mg_recovery"), cellset)
            self.assertNotIn(("1A", "Mg_recovery"), cellset)
            self.assertTrue((out / "master list sources" / ".gitkeep").exists())
            self.assertTrue((out / "gap fill sources" / ".gitkeep").exists())

    def test_compute_builds_nonindustrial_skeleton(self):
        schema = load_schema(COMPUTE_SCHEMA)
        rows = main_input_skeleton_rows(schema)
        params = {row["parameter"] for row in rows}

        self.assertEqual(len(rows), 17)
        self.assertEqual(len([r for r in rows if r["entity"] == GLOBAL_ENTITY_ID]), 4)
        self.assertNotIn("specific_capex", params)
        self.assertFalse(any("yield" in p.lower() for p in params))

        with tempfile.TemporaryDirectory() as tmp:
            build(COMPUTE_SCHEMA, output_dir=tmp)
            written = read_rows(Path(tmp) / "Main Input.csv")
            self.assertEqual({(r["entity"], r["parameter"]) for r in written}, set(schema.skeleton_cells()))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build(TI_SCHEMA, output_dir=tmp, dry_run=True)
            self.assertEqual(result["skeleton_rows"], 74)
            self.assertFalse((Path(tmp) / "Audit.csv").exists())
            self.assertTrue(any("would write" in action[2] for action in result["actions"]))

    def test_existing_nonempty_csvs_are_not_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build(COMPUTE_SCHEMA, output_dir=out)
            audit = out / "Audit.csv"
            audit.write_text("custom\nvalue\n", encoding="utf-8")

            result = build(COMPUTE_SCHEMA, output_dir=out)
            self.assertEqual(audit.read_text(encoding="utf-8"), "custom\nvalue\n")
            self.assertTrue(any(action[0] == "Audit.csv" and action[2].startswith("skip") for action in result["actions"]))

            build(COMPUTE_SCHEMA, output_dir=out, force=True)
            with open(audit, newline="", encoding="utf-8") as fh:
                self.assertEqual(next(csv.reader(fh)), AUDIT_FIELDNAMES)

    def test_pinned_inputs_hook_loads_t8_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_rows(
                out / "pinned-inputs.csv",
                PINNED_INPUTS_FIELDNAMES,
                [
                    {
                        "entity": "compute_hardware",
                        "parameter": "monthly_cost",
                        "raw_value": "100",
                        "raw_units": "USD/month",
                        "raw_basis_year": "2025",
                        "source_key": "pinned-source",
                        "source_url": "https://example.test/pinned",
                        "quality_tag": "D",
                    }
                ],
            )
            result = build(COMPUTE_SCHEMA, output_dir=out)
            self.assertTrue(
                any(action[0] == "pinned-inputs.csv" and "loaded" in action[2] for action in result["actions"])
            )
            audit_rows = read_rows(out / "Audit.csv")
            self.assertEqual(audit_rows[0]["relevance_status"], "pinned")
            main_rows = read_rows(out / "Main Input.csv")
            pinned = [
                row for row in main_rows
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(pinned["pinned"], "TRUE")


if __name__ == "__main__":
    unittest.main()
