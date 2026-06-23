"""Tests for T5 normalization transforms, CLI helpers, and review queues."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from apply_normalization_flags import apply_normalization_flags  # noqa: E402
from lib.csvio import AUDIT_FIELDNAMES, SOURCES_FIELDNAMES, read_header, read_rows, write_rows  # noqa: E402
from lib.extraction import ExtractionHoldError  # noqa: E402
from normalize import normalize_audit  # noqa: E402
from scaffold_conventions import scaffold_conventions  # noqa: E402
from sweep_normalization_flags import NORMALIZATION_FLAGS_FIELDNAMES, sweep_normalization_flags  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
TI_SCHEMA = FIXTURES / "ti-6al-4v.tea-schema.json"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"


def blank_audit_row(**updates):
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "source_key": "src",
            "source_url": "https://example.test/source",
            "page_ref": "p. 1",
            "quality_tag": "A",
            "relevance_status": "clear",
        }
    )
    row.update(updates)
    return row


def write_sources(path: Path):
    write_rows(
        path,
        SOURCES_FIELDNAMES,
        [
            {
                "source_key": "src",
                "title": "Example source",
                "year": "2024",
                "source_url": "https://example.test/source",
                "source_role": "extraction",
            }
        ],
    )


def write_conventions(root: Path, *, index_name: str = "cpi"):
    conv = root / "conventions"
    conv.mkdir()
    write_rows(
        conv / "currency-rates.csv",
        ["from_currency", "to_currency", "year", "rate", "source_note"],
        [
            {"from_currency": "USD", "to_currency": "USD", "year": "2022", "rate": "1"},
            {"from_currency": "USD", "to_currency": "USD", "year": "2024", "rate": "1"},
            {"from_currency": "USD", "to_currency": "USD", "year": "2025", "rate": "1"},
            {"from_currency": "EUR", "to_currency": "USD", "year": "2024", "rate": "1.2"},
        ],
    )
    write_rows(
        conv / "unit-conversions.csv",
        ["from_unit", "to_unit", "factor", "note"],
        [
            {"from_unit": "kWh", "to_unit": "MJ", "factor": "3.6"},
            {"from_unit": "MWh", "to_unit": "kWh", "factor": "1000"},
            {"from_unit": "g", "to_unit": "kg", "factor": "0.001"},
            {"from_unit": "tonne", "to_unit": "kg", "factor": "1000"},
        ],
    )
    write_rows(
        conv / f"{index_name}.csv",
        ["year", "index", "source_note"],
        [
            {"year": "2022", "index": "80"},
            {"year": "2024", "index": "100"},
            {"year": "2025", "index": "110"},
        ],
    )
    write_rows(
        conv / "scaling-exponents.csv",
        ["entity", "default_exponent", "target_scale", "rationale"],
        [{"entity": "1A", "default_exponent": "0.6", "target_scale": "50000"}],
    )
    return conv


class NormalizationTransformTests(unittest.TestCase):
    def test_compute_monetary_uses_cpi_without_industrial_per_kg_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conv = write_conventions(tmp_path, index_name="cpi")
            audit = tmp_path / "Audit.csv"
            out = tmp_path / "Audit_normalized.csv"
            sources = tmp_path / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="REF",
                        parameter="industrial_electricity_price",
                        source_url="",
                        raw_value="$0.10",
                        raw_units="USD/kWh",
                        raw_basis_year="2024",
                    )
                ],
            )

            result = normalize_audit(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                output_path=out,
                conventions_dir=conv,
                sources_path=sources,
            )

            self.assertEqual(result["counts"]["normalized"], 1)
            row = read_rows(out)[0]
            self.assertEqual(row["source_url"], "https://example.test/source")
            self.assertEqual(row["normalized_value"], "0.11")
            self.assertEqual(row["normalized_units"], "USD/kWh")
            self.assertIn("CPI 2024->2025", row["transform_steps"])
            self.assertNotIn("CEPCI", row["transform_steps"])
            self.assertNotIn("/kg", row["normalized_units"])

    def test_ti_rule_types_normalize_by_schema_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conv = write_conventions(tmp_path, index_name="cepci")
            audit = tmp_path / "Audit.csv"
            out = tmp_path / "Audit_normalized.csv"
            sources = tmp_path / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="1A",
                        parameter="electricity",
                        raw_value="3.6",
                        raw_units="MJ/kg TiCl4",
                    ),
                    blank_audit_row(
                        entity="1A",
                        parameter="Ti_yield",
                        raw_value="79.52%",
                        raw_units="chlorination rate",
                    ),
                    blank_audit_row(
                        entity="1A",
                        parameter="specific_capex",
                        raw_value="$4.5M",
                        raw_units="total USD",
                        raw_basis_year="2022",
                        raw_basis_scale="100000",
                        raw_basis_scale_units="tonnes/yr unit output",
                    ),
                ],
            )

            normalize_audit(
                schema_path=TI_SCHEMA,
                audit_path=audit,
                output_path=out,
                conventions_dir=conv,
                sources_path=sources,
            )

            rows = read_rows(out)
            electricity, yield_row, capex = rows
            self.assertEqual(electricity["normalized_value"], "1")
            self.assertEqual(electricity["normalized_units"], "kWh/kg entity output")
            self.assertEqual(yield_row["normalized_value"], "0.7952")
            self.assertIn("fraction", yield_row["normalized_units"])
            self.assertEqual(capex["normalized_value"], "")
            self.assertEqual(capex["capex_usd"], "4500000")
            self.assertEqual(capex["capex_form"], "total")
            self.assertEqual(capex["capex_basis_scale"], "100000")
            self.assertTrue(capex["review_value"])
            self.assertIn("CEPCI 2022->2025", capex["review_steps"])

    def test_rate_passthrough_and_only_quality_tag_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conv = write_conventions(tmp_path, index_name="cpi")
            audit = tmp_path / "Audit.csv"
            out = tmp_path / "Audit_normalized.csv"
            sources = tmp_path / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="throughput",
                        raw_value="2",
                        raw_units="1M tokens/h",
                        quality_tag="D",
                    ),
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="monthly_cost",
                        raw_value="100",
                        raw_units="USD/month",
                        raw_basis_year="2025",
                        quality_tag="E",
                    ),
                ],
            )

            normalize_audit(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                output_path=out,
                conventions_dir=conv,
                sources_path=sources,
                only_quality_tag="E",
            )

            rows = read_rows(out)
            self.assertEqual(rows[0]["normalized_value"], "")
            self.assertEqual(rows[1]["normalized_value"], "100")
            self.assertEqual(rows[1]["normalized_units"], "USD/month")

    def test_unresolved_holds_block_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conv = write_conventions(tmp_path, index_name="cpi")
            audit = tmp_path / "Audit.csv"
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="monthly_cost",
                        raw_value="100",
                        raw_units="USD/month",
                        raw_basis_year="2025",
                        relevance_status="hold",
                    )
                ],
            )
            with self.assertRaises(ExtractionHoldError):
                normalize_audit(
                    schema_path=COMPUTE_SCHEMA,
                    audit_path=audit,
                    conventions_dir=conv,
                    sources_path=None,
                    dry_run=True,
                )


class NormalizationQueueTests(unittest.TestCase):
    def test_sweep_and_apply_reject_flagged_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conv = write_conventions(tmp_path, index_name="cpi")
            audit = tmp_path / "Audit.csv"
            normalized = tmp_path / "Audit_normalized.csv"
            queue = tmp_path / "normalization_flags.csv"
            sources = tmp_path / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    blank_audit_row(
                        entity="compute_hardware",
                        parameter="monthly_cost",
                        raw_value="100 or 200",
                        raw_units="USD/month",
                        raw_basis_year="2025",
                    )
                ],
            )

            normalize_audit(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                output_path=normalized,
                conventions_dir=conv,
                sources_path=sources,
            )
            flagged = sweep_normalization_flags(audit_path=normalized, output_path=queue)
            self.assertEqual(len(flagged["rows"]), 1)
            queued = read_rows(queue)
            self.assertEqual(queued[0]["source_url"], "https://example.test/source")
            self.assertIn("multiple numeric candidates", queued[0]["flag_reason"])
            queued[0]["proposed_action"] = "reject"
            queued[0]["analyst_answer"] = "Two candidate values; no basis for choosing."
            write_rows(queue, NORMALIZATION_FLAGS_FIELDNAMES, queued)

            result = apply_normalization_flags(audit_path=normalized, queue_path=queue)
            self.assertEqual(result["counts"]["reject"], 1)
            row = read_rows(normalized)[0]
            self.assertEqual(row["normalization_status"], "reject")
            self.assertEqual(row["normalized_value"], "")
            self.assertIn("REJECTED by normalization review", row["transform_steps"])

    def test_scaffold_conventions_follows_schema_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compute_out = tmp_path / "compute-conventions"
            ti_out = tmp_path / "ti-conventions"

            scaffold_conventions(schema_path=COMPUTE_SCHEMA, output_dir=compute_out)
            self.assertTrue((compute_out / "cpi.csv").exists())
            self.assertFalse((compute_out / "cepci.csv").exists())
            self.assertEqual(read_header(compute_out / "cpi.csv"), ["year", "index", "source_note"])
            self.assertTrue(read_rows(compute_out / "unit-conversions.csv"))

            scaffold_conventions(schema_path=TI_SCHEMA, output_dir=ti_out)
            self.assertTrue((ti_out / "cepci.csv").exists())
            self.assertTrue((ti_out / "scaling-exponents.csv").exists())


if __name__ == "__main__":
    unittest.main()
