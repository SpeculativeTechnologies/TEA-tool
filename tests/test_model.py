"""Tests for the model layer: the model.py contract + the check_model smoke checker.

Proves the single bespoke model template honors the /tea-model contract and that
the SAME file reads both the quick dummy CSV (entity,parameter,value) and the
pipeline's Main Input.csv (unit,field,normalized_value) — the dummy->real swap.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_model  # noqa: E402

TEMPLATE = ROOT / "templates" / "model.template.py"

DUMMY_INPUTS = (
    "entity,parameter,value\n"
    "compute_hardware,cost_per_fu,1.20\n"
    "power_cooling,cost_per_fu,0.35\n"
    "networking,cost_per_fu,0.10\n"
)

# Pipeline-shaped inputs: aliased columns unit/field/normalized_value.
MAIN_INPUT = (
    "unit,field,normalized_value,capex_usd\n"
    "compute_hardware,cost_per_fu,1.50,\n"
    "power_cooling,cost_per_fu,0.40,\n"
)


class CheckModelTests(unittest.TestCase):
    def _check(self, inputs_text):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        model = Path(tmp) / "model.py"
        shutil.copyfile(TEMPLATE, model)
        inputs = Path(tmp) / "inputs.csv"
        inputs.write_text(inputs_text, encoding="utf-8")
        return check_model.check_model(model, inputs, outdir=Path(tmp) / "plots")

    def test_template_passes_on_dummy_inputs(self):
        result = self._check(DUMMY_INPUTS)
        self.assertTrue(result["ok"], result["problems"])
        self.assertIn("cost_breakdown.png", result["plots"])
        self.assertIn("total_cost_per_fu", result["headline"])

    def test_same_model_reads_pipeline_main_input_columns(self):
        result = self._check(MAIN_INPUT)
        self.assertTrue(result["ok"], result["problems"])
        # 1.50 + 0.40 via the unit/field/normalized_value aliases.
        self.assertAlmostEqual(result["headline"]["total_cost_per_fu"], 1.90, places=6)

    def test_check_model_flags_missing_model(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        inputs = Path(tmp) / "inputs.csv"
        inputs.write_text(DUMMY_INPUTS, encoding="utf-8")
        result = check_model.check_model(Path(tmp) / "missing.py", inputs)
        self.assertFalse(result["ok"])


class ExampleModelTests(unittest.TestCase):
    """The worked compute-service example honors the contract (covers tornado())."""

    def test_compute_service_example_passes(self):
        model = ROOT / "examples" / "compute-service" / "model.py"
        inputs = ROOT / "examples" / "compute-service" / "model" / "dummy-inputs.csv"
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        result = check_model.check_model(
            model, inputs, expect=["cost_breakdown.png", "tornado.png"], outdir=Path(tmp) / "plots"
        )
        self.assertTrue(result["ok"], result["problems"])
        self.assertIn("cost_per_1m_tokens_usd", result["headline"])


if __name__ == "__main__":
    unittest.main()
