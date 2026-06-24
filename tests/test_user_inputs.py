"""Tests for analyst user inputs, fixed precedence, and no-gap finalization."""

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
from lib.consolidation import FixedInputConflictError, select_rows  # noqa: E402
from lib.csvio import (  # noqa: E402
    AUDIT_FIELDNAMES,
    MAIN_INPUT_FIELDNAMES,
    SOURCES_FIELDNAMES,
    USER_INPUTS_FIELDNAMES,
    blank_row,
    read_rows,
    write_rows,
)
from lib.schema import load_schema  # noqa: E402
from lib.shared_inputs import satisfied_cells_from_rows  # noqa: E402
from lib.user_inputs import UserInputError, materialize_user_inputs  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"


def build_run(tmp) -> Path:
    """Build a run folder with the compute schema placed inside it, like a real run."""

    run_dir = Path(tmp) / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(COMPUTE_SCHEMA, run_dir / "tea-schema.json")
    build(run_dir / "tea-schema.json", output_dir=run_dir)
    return run_dir


def audit_row(**updates):
    row = blank_row(AUDIT_FIELDNAMES)
    row.update({"relevance_status": "clear", "quality_tag": "A", "page_ref": "p1"})
    row.update(updates)
    return row


def write_user_files(run_dir: Path, inputs: list[dict], sources: list[dict] | None = None) -> None:
    write_rows(
        run_dir / "user-sources.csv",
        SOURCES_FIELDNAMES,
        sources
        or [
            {
                "source_key": "analyst-batch",
                "title": "Conversational submission",
                "year": "2026",
                "source_url": "https://internal.note/analyst",
                "source_role": "analyst",
            }
        ],
    )
    write_rows(run_dir / "user-inputs.csv", USER_INPUTS_FIELDNAMES, inputs)


class MaterializationTests(unittest.TestCase):
    def _build(self, tmp) -> Path:
        return build_run(tmp)

    def test_registers_analyst_source_and_input_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(tmp)
            write_user_files(
                run_dir,
                [
                    {
                        "input_id": "ui-001",
                        "entity": "compute_hardware",
                        "parameter": "monthly_cost",
                        "raw_value": "5000",
                        "raw_units": "USD/month",
                        "raw_basis_year": "2025",
                        "source_key": "analyst-batch",
                        "page_ref": "chat",
                        "quality_tag": "A",
                        "input_origin": "analyst",
                        "fixed": "TRUE",
                        "user_rationale": "Customer contract price",
                    }
                ],
            )
            result = materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            self.assertEqual(result["inputs"], 1)
            self.assertEqual(result["fixed"], 1)

            sources = read_rows(run_dir / "Sources.csv")
            self.assertTrue(any(s["source_role"] == "analyst" for s in sources))

            analyst_rows = [r for r in read_rows(run_dir / "Audit.csv") if r["input_origin"] == "analyst"]
            self.assertEqual(len(analyst_rows), 1)
            row = analyst_rows[0]
            self.assertEqual(row["input_priority"], "fixed")
            self.assertEqual(row["relevance_status"], "clear")
            self.assertEqual(row["source_url"], "https://internal.note/analyst")
            self.assertIn("user_input_id=ui-001", row["notes"])

    def test_rerun_is_idempotent_by_input_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(tmp)
            write_user_files(
                run_dir,
                [
                    {
                        "input_id": "ui-001",
                        "entity": "compute_hardware",
                        "parameter": "monthly_cost",
                        "raw_value": "5000",
                        "raw_units": "USD/month",
                        "raw_basis_year": "2025",
                        "source_key": "analyst-batch",
                        "input_origin": "analyst",
                        "fixed": "TRUE",
                    }
                ],
            )
            materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            analyst_rows = [r for r in read_rows(run_dir / "Audit.csv") if r["input_origin"] == "analyst"]
            self.assertEqual(len(analyst_rows), 1)

    def test_uploaded_evidence_retains_extracted_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(tmp)
            write_user_files(
                run_dir,
                [
                    {
                        "input_id": "ui-doc",
                        "entity": "compute_hardware",
                        "parameter": "monthly_cost",
                        "raw_value": "4200",
                        "raw_units": "USD/month",
                        "raw_basis_year": "2025",
                        "source_key": "analyst-batch",
                        "input_origin": "extracted",
                        "fixed": "TRUE",
                    }
                ],
            )
            materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            row = [r for r in read_rows(run_dir / "Audit.csv") if "user_input_id=ui-doc" in r["notes"]][0]
            self.assertEqual(row["input_origin"], "extracted")
            self.assertEqual(row["input_priority"], "fixed")

    def test_conflicting_fixed_inputs_block_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(tmp)
            base = {
                "entity": "compute_hardware",
                "parameter": "monthly_cost",
                "raw_units": "USD/month",
                "raw_basis_year": "2025",
                "source_key": "analyst-batch",
                "input_origin": "analyst",
                "fixed": "TRUE",
            }
            write_user_files(
                run_dir,
                [
                    {"input_id": "ui-001", "raw_value": "5000", **base},
                    {"input_id": "ui-002", "raw_value": "9000", **base},
                ],
            )
            with self.assertRaises(UserInputError) as ctx:
                materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            self.assertIn("disagreeing fixed", str(ctx.exception))

    def test_unmappable_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(tmp)
            write_user_files(
                run_dir,
                [
                    {
                        "input_id": "ui-x",
                        "entity": "compute_hardware",
                        "parameter": "not_a_parameter",
                        "raw_value": "1",
                        "source_key": "analyst-batch",
                        "input_origin": "analyst",
                    }
                ],
            )
            with self.assertRaises(UserInputError) as ctx:
                materialize_user_inputs(schema_path=run_dir / "tea-schema.json", run_dir=run_dir)
            self.assertIn("unknown parameter", str(ctx.exception))


class FixedPrecedenceTests(unittest.TestCase):
    def test_fixed_candidate_wins_over_better_quality(self):
        schema = load_schema(COMPUTE_SCHEMA)
        rows = [
            audit_row(
                entity="compute_hardware", parameter="monthly_cost", source_key="paper",
                quality_tag="A", normalized_value="1000", normalized_units="USD/month",
                input_origin="extracted",
            ),
            audit_row(
                entity="compute_hardware", parameter="monthly_cost", source_key="analyst-batch",
                quality_tag="C", normalized_value="5000", normalized_units="USD/month",
                input_origin="analyst", input_priority="fixed",
            ),
        ]
        selected = select_rows(rows, schema)
        winner = [r for r in selected if r["selected_for_model"] == "TRUE"]
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0]["source_key"], "analyst-batch")
        self.assertEqual(winner[0]["input_priority"], "fixed")

    def test_two_disagreeing_fixed_inputs_block_consolidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit_normalized.csv"
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(
                        entity="compute_hardware", parameter="monthly_cost", source_key="a",
                        normalized_value="5000", normalized_units="USD/month",
                        input_origin="analyst", input_priority="fixed",
                    ),
                    audit_row(
                        entity="compute_hardware", parameter="monthly_cost", source_key="b",
                        normalized_value="9000", normalized_units="USD/month",
                        input_origin="extracted", input_priority="fixed",
                    ),
                ],
            )
            with self.assertRaises(FixedInputConflictError):
                consolidate(
                    schema_path=COMPUTE_SCHEMA,
                    audit_path=audit,
                    main_input_path=root / "Main Input.csv",
                    sources_path=None,
                    scope_fit_decisions_path=None,
                )

    def test_fixed_shared_input_is_selected(self):
        schema = load_schema(COMPUTE_SCHEMA)
        rows = [
            audit_row(
                entity="compute_hardware", parameter="monthly_cost", source_key="paper",
                quality_tag="A", normalized_value="1000", normalized_units="USD/month",
                input_origin="extracted",
            ),
            audit_row(
                entity="compute_hardware", parameter="monthly_cost", source_key="shared-src",
                quality_tag="C", normalized_value="3000", normalized_units="USD/month",
                input_origin="shared", input_priority="fixed",
            ),
        ]
        selected = select_rows(rows, schema)
        winner = [r for r in selected if r["selected_for_model"] == "TRUE"][0]
        self.assertEqual(winner["source_key"], "shared-src")
        self.assertEqual(winner["input_origin"], "shared")
        self.assertEqual(winner["input_priority"], "fixed")

    def test_candidate_analyst_evidence_does_not_satisfy_cell(self):
        rows = [
            {"entity": "compute_hardware", "parameter": "monthly_cost", "input_origin": "analyst", "input_priority": ""},
            {"entity": "power_cooling", "parameter": "monthly_cost", "input_origin": "analyst", "input_priority": "fixed"},
            {"entity": "networking", "parameter": "monthly_cost", "input_origin": "shared", "input_priority": ""},
        ]
        satisfied = satisfied_cells_from_rows(rows)
        # Non-fixed analyst candidate evidence does NOT suppress research.
        self.assertNotIn(("compute_hardware", "monthly_cost"), satisfied)
        # Fixed inputs and shared inputs do.
        self.assertIn(("power_cooling", "monthly_cost"), satisfied)
        self.assertIn(("networking", "monthly_cost"), satisfied)


class NoGapFinalizationTests(unittest.TestCase):
    def _fill_all(self, run_dir: Path) -> None:
        rows = read_rows(run_dir / "Main Input.csv", required_columns=MAIN_INPUT_FIELDNAMES)
        for row in rows:
            row["normalized_value"] = "1"
            row["normalized_units"] = "unit"
            row["quality_tag"] = "B"
        write_rows(run_dir / "Main Input.csv", MAIN_INPUT_FIELDNAMES, rows)

    def test_guided_mode_blocks_on_gaps_and_passes_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = build_run(tmp)  # default guided mode
            write_rows(run_dir / "Sources.csv", SOURCES_FIELDNAMES, [])
            with self.assertRaisesRegex(ValueError, "every TEA cell"):
                finalize_inputs(
                    schema_path=run_dir / "tea-schema.json",
                    main_input_path=run_dir / "Main Input.csv",
                    sources_path=run_dir / "Sources.csv",
                    output_dir=run_dir / "final",
                )
            self._fill_all(run_dir)
            result = finalize_inputs(
                schema_path=run_dir / "tea-schema.json",
                main_input_path=run_dir / "Main Input.csv",
                sources_path=run_dir / "Sources.csv",
                output_dir=run_dir / "final",
            )
            self.assertEqual(result["gaps"], 0)


if __name__ == "__main__":
    unittest.main()
