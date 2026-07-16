"""Auto-mode setup and finalization contract tests."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_csvs import build  # noqa: E402
from finalize_inputs import finalize_inputs  # noqa: E402
from lib.csvio import MAIN_INPUT_FIELDNAMES, read_rows, write_rows  # noqa: E402
from lib.schema import load_schema, validate_schema  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "compute-service.tea-schema.json"


class AutoModeTests(unittest.TestCase):
    def _schema(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _numeric_auto_schema(self) -> dict:
        data = self._schema()
        data["execution_mode"] = "auto"
        data["parameters"] = [
            parameter for parameter in data["parameters"] if parameter["rule_type"] not in {"JSON", "TEXT"}
        ]
        return data

    def test_mode_defaults_to_human_gates(self):
        self.assertEqual(load_schema(FIXTURE).execution_mode, "auto_with_human_gates")

    def test_invalid_mode_is_rejected(self):
        data = self._schema()
        data["execution_mode"] = "mostly_auto"
        report = validate_schema(data)
        self.assertTrue(any("execution_mode" in error for error in report.errors))

    def test_non_numeric_parameter_contracts_rejected_in_both_modes(self):
        # The numeric-only contract rejects JSON/TEXT parameters in Guided and
        # Auto alike; inject one (the fixtures are numeric-only) and confirm.
        for mode in ("auto_with_human_gates", "auto"):
            with self.subTest(mode=mode):
                data = self._schema()
                data["execution_mode"] = mode
                data["parameters"].append(
                    {"id": "free_text", "label": "Free text", "rule_type": "TEXT", "applies_to": "all"}
                )
                report = validate_schema(data)
                self.assertTrue(any("JSON/TEXT" in error for error in report.errors), report.errors)

    def test_auto_finalization_rejects_blank_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self._numeric_auto_schema()
            schema_path = root / "tea-schema.json"
            schema_path.write_text(json.dumps(data), encoding="utf-8")
            build(schema_path, output_dir=root)

            with self.assertRaisesRegex(ValueError, "every TEA cell"):
                finalize_inputs(
                    schema_path=schema_path,
                    main_input_path=root / "Main Input.csv",
                    sources_path=root / "Sources.csv",
                    output_dir=root / "final",
                )

    def test_auto_finalization_writes_review_when_all_cells_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self._numeric_auto_schema()
            schema_path = root / "tea-schema.json"
            schema_path.write_text(json.dumps(data), encoding="utf-8")
            build(schema_path, output_dir=root)

            rows = read_rows(root / "Main Input.csv", required_columns=MAIN_INPUT_FIELDNAMES)
            for row in rows:
                row["normalized_value"] = "1"
                row["normalized_units"] = "unit"
                row["quality_tag"] = "E"
                row["estimate_justification"] = json.dumps(
                    {
                        "method": "single_anchor",
                        "loop": 1,
                        "enabling_assumption": "Test system is analogous to the fixture anchor.",
                        "equation": "value = anchor",
                        "derivation_steps": ["Use fixture anchor value 1."],
                        "anchor": {
                            "source_key": "fixture-anchor",
                            "page_ref": "Table 1",
                        },
                        "estimator_confidence": "low",
                        "caveats": ["AUTO assumption"],
                    }
                )
            write_rows(root / "Main Input.csv", MAIN_INPUT_FIELDNAMES, rows)
            (root / "auto-run-log.md").write_text(
                "### Assumptions and flags\n\n- AUTO: placeholder test assumption.\n",
                encoding="utf-8",
            )

            result = finalize_inputs(
                schema_path=schema_path,
                main_input_path=root / "Main Input.csv",
                sources_path=root / "Sources.csv",
                output_dir=root / "final",
            )
            self.assertEqual(result["gaps"], 0)
            review = (root / "final" / "auto-review.md").read_text(encoding="utf-8")
            self.assertIn("Numeric TEA cells completed", review)
            self.assertIn("placeholder test assumption", review)

    def test_finalization_rejects_estimates_created_outside_phase_6(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self._numeric_auto_schema()
            schema_path = root / "tea-schema.json"
            schema_path.write_text(json.dumps(data), encoding="utf-8")
            build(schema_path, output_dir=root)

            rows = read_rows(root / "Main Input.csv", required_columns=MAIN_INPUT_FIELDNAMES)
            for row in rows:
                row["normalized_value"] = "1"
                row["normalized_units"] = "unit"
                row["quality_tag"] = "E"
                row["estimate_justification"] = json.dumps(
                    {"note": "generic research worker supplied a point estimate"}
                )
            write_rows(root / "Main Input.csv", MAIN_INPUT_FIELDNAMES, rows)

            with self.assertRaisesRegex(ValueError, "must be created through Phase 6"):
                finalize_inputs(
                    schema_path=schema_path,
                    main_input_path=root / "Main Input.csv",
                    sources_path=root / "Sources.csv",
                    output_dir=root / "final",
                )


if __name__ == "__main__":
    unittest.main()
