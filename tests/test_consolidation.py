"""Tests for T6 consolidation and value-disagreement review."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from apply_value_disagreements import apply_value_disagreements  # noqa: E402
from consolidate import consolidate  # noqa: E402
from lib.consolidation import ScopeFitDecisionRowsError, ValueDisagreementRowsError  # noqa: E402
from lib.csvio import (  # noqa: E402
    AUDIT_FIELDNAMES,
    CSV_SCHEMAS,
    SOURCES_FIELDNAMES,
    column_names,
    read_rows,
    write_rows,
)
from sweep_value_disagreements import VALUE_DISAGREEMENTS_FIELDNAMES, sweep_value_disagreements  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"


def audit_row(**updates):
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "entity": "compute_hardware",
            "parameter": "monthly_cost",
            "source_key": "src-a",
            "source_url": "https://example.test/a",
            "page_ref": "p. 1",
            "raw_value": "100",
            "raw_units": "USD/month",
            "raw_basis_year": "2024",
            "quality_tag": "B",
            "normalized_value": "110",
            "normalized_units": "USD/month",
            "transform_steps": "CPI 2024->2025",
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
            {"source_key": "src-a", "source_url": "https://example.test/a", "source_role": "extraction"},
            {"source_key": "src-b", "source_url": "https://example.test/b", "source_role": "extraction"},
            {"source_key": "src-c", "source_url": "https://example.test/c", "source_role": "extraction"},
        ],
    )


class ConsolidationTests(unittest.TestCase):
    def test_selects_best_quality_and_writes_main_input_with_source_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit_normalized.csv"
            main = root / "Main Input.csv"
            sidecar = root / "Audit_normalized_consolidated.csv"
            sources = root / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(source_key="src-a", quality_tag="C", normalized_value="110"),
                    audit_row(
                        source_key="src-b",
                        source_url="",
                        quality_tag="A",
                        raw_basis_year="2025",
                        normalized_value="120",
                    ),
                ],
            )

            result = consolidate(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=main,
                sources_path=sources,
                scope_fit_decisions_path=None,
            )

            self.assertEqual(result["selected"], 1)
            audit_rows = read_rows(sidecar)
            selected = [row for row in audit_rows if row["selected_for_model"] == "TRUE"]
            self.assertEqual(selected[0]["source_key"], "src-b")
            self.assertEqual(selected[0]["source_url"], "https://example.test/b")
            self.assertIn("vs [src-a]", selected[0]["cross_check_delta"])

            main_rows = read_rows(main)
            cell = [
                row for row in main_rows
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(cell["source_key"], "src-b")
            self.assertEqual(cell["source_url"], "https://example.test/b")
            self.assertEqual(cell["normalized_value"], "120")
            self.assertEqual(len(main_rows), 17)

    def test_pinned_row_wins_over_better_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit_normalized.csv"
            main = root / "Main Input.csv"
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(source_key="src-a", quality_tag="A", normalized_value="100"),
                    audit_row(
                        source_key="src-b",
                        quality_tag="D",
                        normalized_value="95",
                        relevance_status="pinned",
                    ),
                ],
            )

            consolidate(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=main,
                sources_path=None,
                scope_fit_decisions_path=None,
            )

            cell = [
                row for row in read_rows(main)
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(cell["source_key"], "src-b")
            self.assertEqual(cell["pinned"], "TRUE")
            audit_rows = read_rows(root / "Audit_normalized_consolidated.csv")
            selected = [row for row in audit_rows if row["source_key"] == "src-b"][0]
            runner_up = [row for row in audit_rows if row["source_key"] == "src-a"][0]
            self.assertEqual(runner_up["selected_for_model"], "FALSE")
            self.assertIn("vs [src-a]", selected["cross_check_delta"])

    def test_scope_fit_decision_required_for_same_quality_top_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit_normalized.csv"
            main = root / "Main Input.csv"
            decisions = root / "stage5_scope_fit_decisions.csv"
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(source_key="src-a", quality_tag="A", normalized_value="100"),
                    audit_row(source_key="src-b", quality_tag="A", normalized_value="105"),
                ],
            )

            with self.assertRaises(ScopeFitDecisionRowsError):
                consolidate(
                    schema_path=COMPUTE_SCHEMA,
                    audit_path=audit,
                    main_input_path=main,
                    sources_path=None,
                    scope_fit_decisions_path=None,
                    value_disagreement_threshold=1.0,
                )

            rows = [{name: "" for name in column_names(CSV_SCHEMAS["stage5_scope_fit_decisions.csv"])}]
            rows[0].update(
                {
                    "entity": "compute_hardware",
                    "parameter": "monthly_cost",
                    "source_key": "src-b",
                    "decision": "src-b",
                    "rationale": "Best match to reserved GPU fleet scope.",
                }
            )
            write_rows(decisions, column_names(CSV_SCHEMAS["stage5_scope_fit_decisions.csv"]), rows)

            consolidate(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=main,
                sources_path=None,
                scope_fit_decisions_path=decisions,
                value_disagreement_threshold=1.0,
            )
            selected = [
                row for row in read_rows(root / "Audit_normalized_consolidated.csv")
                if row["selected_for_model"] == "TRUE"
            ][0]
            self.assertEqual(selected["source_key"], "src-b")


class ValueDisagreementTests(unittest.TestCase):
    def test_sweep_apply_reject_then_consolidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit_normalized.csv"
            main = root / "Main Input.csv"
            queue = root / "value_disagreements.csv"
            sources = root / "Sources.csv"
            write_sources(sources)
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(source_key="src-a", quality_tag="A", normalized_value="100"),
                    audit_row(
                        source_key="src-b",
                        source_url="",
                        quality_tag="A",
                        normalized_value="1000",
                    ),
                ],
            )

            with self.assertRaises(ValueDisagreementRowsError):
                consolidate(
                    schema_path=COMPUTE_SCHEMA,
                    audit_path=audit,
                    main_input_path=main,
                    sources_path=sources,
                    scope_fit_decisions_path=None,
                )

            swept = sweep_value_disagreements(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                output_path=queue,
                sources_path=sources,
            )
            self.assertEqual(len(swept["rows"]), 2)
            queued = read_rows(queue)
            self.assertEqual(queued[0]["source_url"], "https://example.test/a")
            queued[1]["proposed_verdict"] = "reject"
            queued[1]["analyst_answer"] = "Outlier is a different service boundary."
            write_rows(queue, VALUE_DISAGREEMENTS_FIELDNAMES, queued)

            applied = apply_value_disagreements(audit_path=audit, queue_path=queue)
            self.assertEqual(applied["counts"]["reject"], 1)
            rejected = [row for row in read_rows(audit) if row["source_key"] == "src-b"][0]
            self.assertEqual(rejected["disagreement_status"], "reject")
            self.assertEqual(rejected["normalized_value"], "")

            consolidate(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=main,
                sources_path=sources,
                scope_fit_decisions_path=None,
            )
            cell = [
                row for row in read_rows(main)
                if row["entity"] == "compute_hardware" and row["parameter"] == "monthly_cost"
            ][0]
            self.assertEqual(cell["source_key"], "src-a")


if __name__ == "__main__":
    unittest.main()
