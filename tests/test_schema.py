"""Tests for lib/schema.py and templates/tea-schema.schema.json (T1).

Proves the T1 acceptance criteria:
- The Ti (industrial) and compute (non-industrial) example configs both
  validate cleanly.
- Ambiguous input (e.g. a parameter with no declared units) yields a logged
  *open question*, not a silent default and not a hard error.

Also exercises the Schema accessor API that T2-T8 depend on.

The fixtures here are provisional, representative instances. T10 owns the
authoritative example configs (examples/ti-6al-4v/, examples/compute-service/)
and the Run-2 regression oracle. These tests assert internal consistency and
the validation contract, not Run-2 numeric fidelity.

Run:  python -m unittest discover -s tests
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib.schema import (  # noqa: E402
    GLOBAL_ENTITY_ID,
    Schema,
    SchemaError,
    load_json_schema,
    load_schema,
    validate_schema,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TI = "ti-6al-4v.tea-schema.json"
COMPUTE = "compute-service.tea-schema.json"


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


class FixtureValidationTests(unittest.TestCase):
    """Both example configs validate with no errors, open questions, warnings."""

    def test_ti_validates_clean(self):
        report = validate_schema(load_fixture(TI))
        self.assertEqual(report.errors, [], "Ti config should have no hard errors")
        self.assertEqual([str(q) for q in report.open_questions], [])
        self.assertEqual(report.warnings, [])
        self.assertTrue(report.ok)

    def test_compute_validates_clean(self):
        report = validate_schema(load_fixture(COMPUTE))
        self.assertEqual(report.errors, [])
        self.assertEqual([str(q) for q in report.open_questions], [])
        self.assertEqual(report.warnings, [])
        self.assertTrue(report.ok)

    def test_load_schema_returns_wrapped_schema(self):
        s = load_schema(FIXTURES / TI)
        self.assertIsInstance(s, Schema)
        self.assertEqual(s.tea_id, "ti-6al-4v-incumbent")
        self.assertEqual(s.functional_unit_name, "kg Ti-6Al-4V billet")

    def test_compute_needs_no_industrial_features(self):
        """The non-industrial config uses no FRACTION, CAPEX, or CEPCI path."""
        s = load_schema(FIXTURES / COMPUTE)
        rule_types = {p["rule_type"] for p in s.parameters}
        self.assertNotIn("FRACTION", rule_types)
        self.assertNotIn("CAPEX", rule_types)
        self.assertNotEqual(s.inflation_index, "CEPCI")
        self.assertIsNone(s.comparable_rubric)


class StructuralErrorTests(unittest.TestCase):
    def test_reserved_ref_entity_rejected(self):
        data = copy.deepcopy(load_fixture(TI))
        data["entities"].append(
            {"id": "REF", "name": "bad", "estimation_policy": "first_principles_only"}
        )
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("reserved" in e.lower() for e in report.errors), report.errors)

    def test_unknown_top_level_key_rejected(self):
        data = copy.deepcopy(load_fixture(TI))
        data["bogus_key"] = 1
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("bogus_key" in e for e in report.errors), report.errors)

    def test_bad_rule_type_rejected(self):
        data = copy.deepcopy(load_fixture(TI))
        data["parameters"][0]["rule_type"] = "WRONG"
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("rule_type" in e for e in report.errors), report.errors)

    def test_bad_inflation_index_rejected(self):
        data = copy.deepcopy(load_fixture(TI))
        data["basis"]["inflation_index"] = "RPI"
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("inflation_index" in e for e in report.errors), report.errors)

    def test_missing_required_top_level_key_rejected(self):
        data = copy.deepcopy(load_fixture(TI))
        del data["functional_unit"]
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("functional_unit" in e for e in report.errors), report.errors)


class CrossReferenceTests(unittest.TestCase):
    def test_applies_to_unknown_entity_is_error(self):
        data = copy.deepcopy(load_fixture(TI))
        for p in data["parameters"]:
            if p["id"] == "consumables.argon":
                p["applies_to"] = ["1B", "ZZ"]
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("ZZ" in e and "applies_to" in e for e in report.errors), report.errors)

    def test_duplicate_parameter_id_is_error(self):
        data = copy.deepcopy(load_fixture(TI))
        data["parameters"].append(copy.deepcopy(data["parameters"][0]))
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("duplicate" in e for e in report.errors), report.errors)

    def test_comparables_policy_without_rubric_is_error(self):
        data = copy.deepcopy(load_fixture(COMPUTE))
        data["entities"][0]["estimation_policy"] = "comparables_first"
        report = validate_schema(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("comparable_rubric" in e for e in report.errors), report.errors)


class OpenQuestionTests(unittest.TestCase):
    """The headline T1 acceptance: ambiguity -> open question, not a default."""

    def test_missing_intensity_units_is_open_question_not_error(self):
        data = copy.deepcopy(load_fixture(TI))
        for p in data["parameters"]:
            if p["id"] == "electricity":
                del p["numerator_units"]
        report = validate_schema(data)
        # Structurally valid: no hard error, loads fine.
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.errors, [])
        # But the ambiguity is logged as an open question.
        matches = [q for q in report.open_questions if "electricity" in q.where]
        self.assertEqual(len(matches), 1, [str(q) for q in report.open_questions])
        self.assertIn("numerator_units", matches[0].question)

    def test_missing_units_does_not_get_silently_defaulted(self):
        data = copy.deepcopy(load_fixture(TI))
        for p in data["parameters"]:
            if p["id"] == "electricity":
                del p["numerator_units"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tea-schema.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            s = load_schema(path)  # strict=True must NOT raise — it's an open question
        self.assertNotIn("numerator_units", s.parameter("electricity"))  # no invented default
        self.assertTrue(any("electricity" in q.where for q in s.report.open_questions))

    def test_missing_scope_frame_is_open_question(self):
        data = copy.deepcopy(load_fixture(TI))
        del data["entities"][0]["scope_frame"]
        report = validate_schema(data)
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("scope_frame" in q.question for q in report.open_questions))

    def test_reference_value_missing_canonical_unit_is_open_question(self):
        data = copy.deepcopy(load_fixture(TI))
        for p in data["parameters"]:
            if p["id"] == "electricity_price":
                del p["canonical_unit"]
        report = validate_schema(data)
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("canonical_unit" in q.question for q in report.open_questions))

    def test_open_questions_render_to_markdown(self):
        data = copy.deepcopy(load_fixture(TI))
        del data["entities"][0]["scope_frame"]
        report = validate_schema(data)
        md = report.render_open_questions_md(tea_id="ti-6al-4v-incumbent")
        self.assertIn("open questions", md.lower())
        self.assertIn("scope_frame", md)


class LoadingTests(unittest.TestCase):
    def test_load_schema_raises_on_hard_error(self):
        data = copy.deepcopy(load_fixture(TI))
        data["parameters"].append(copy.deepcopy(data["parameters"][0]))  # dup id
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tea-schema.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SchemaError):
                load_schema(path)
            # strict=False loads anyway, surfacing errors on the report.
            s = load_schema(path, strict=False)
            self.assertFalse(s.report.ok)

    def test_load_schema_missing_file_raises(self):
        with self.assertRaises(SchemaError):
            load_schema(FIXTURES / "does-not-exist.json")

    def test_load_schema_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(SchemaError):
                load_schema(path)


class AccessorTests(unittest.TestCase):
    def setUp(self):
        self.ti = Schema(load_fixture(TI))
        self.compute = Schema(load_fixture(COMPUTE))

    def test_entity_and_parameter_ids(self):
        self.assertEqual(self.ti.entity_ids, ["1A", "1B", "1C", "2A", "2B", "4", "5", "6"])
        self.assertIn("specific_capex", self.ti.parameter_ids)

    def test_parameters_for_respects_applies_to(self):
        ids_1c = [p["id"] for p in self.ti.parameters_for("1C")]
        self.assertIn("Mg_recovery", ids_1c)
        self.assertIn("electricity", ids_1c)          # applies_to "all"
        self.assertNotIn("Ti_yield", ids_1c)          # not applied to 1C
        self.assertNotIn("electricity_price", ids_1c)  # reference value -> global only

    def test_parameters_for_global_entity_returns_reference_values(self):
        ref_ids = {p["id"] for p in self.ti.parameters_for(GLOBAL_ENTITY_ID)}
        self.assertEqual(
            ref_ids,
            {"electricity_price", "natural_gas_price", "al_v_master_alloy_price"},
        )

    def test_applies(self):
        self.assertTrue(self.ti.applies("Mg_recovery", "1C"))
        self.assertFalse(self.ti.applies("Mg_recovery", "1A"))
        self.assertTrue(self.ti.applies("electricity", "1A"))
        self.assertTrue(self.ti.applies("electricity_price", GLOBAL_ENTITY_ID))
        self.assertFalse(self.ti.applies("electricity_price", "1A"))
        self.assertFalse(self.ti.applies("electricity", GLOBAL_ENTITY_ID))

    def test_skeleton_cells_structure(self):
        cells = self.ti.skeleton_cells()
        cellset = set(cells)
        # No accidental duplicates.
        self.assertEqual(len(cells), len(cellset))
        # Reference values appear only under REF; real cells never carry them.
        self.assertIn((GLOBAL_ENTITY_ID, "electricity_price"), cellset)
        self.assertNotIn(("1A", "electricity_price"), cellset)
        # Real entity cells respect applies_to.
        self.assertIn(("1A", "consumables.cl2_makeup"), cellset)
        self.assertIn(("1C", "Mg_recovery"), cellset)
        self.assertNotIn(("1A", "Mg_recovery"), cellset)
        # REF rows are exactly the reference-value parameters.
        ref_rows = {p for e, p in cells if e == GLOBAL_ENTITY_ID}
        self.assertEqual(
            ref_rows, {"electricity_price", "natural_gas_price", "al_v_master_alloy_price"}
        )
        # Count is internally consistent with the accessor logic.
        expected = sum(len(self.ti.parameters_for(e)) for e in self.ti.entity_ids)
        expected += len(self.ti.reference_value_parameters)
        self.assertEqual(len(cells), expected)

    def test_reference_and_context_free_lists(self):
        self.assertEqual(len(self.ti.reference_value_parameters), 3)
        self.assertEqual(len(self.ti.context_free_parameters), 3)
        entity_param_ids = {p["id"] for p in self.ti.entity_parameters}
        self.assertNotIn("electricity_price", entity_param_ids)

    def test_search_targetable_accessor(self):
        self.assertTrue(self.ti.is_search_targetable("electricity"))
        self.assertFalse(self.ti.is_search_targetable("feedstock_quantity"))
        targetable_ids = {p["id"] for p in self.ti.search_targetable_parameters}
        self.assertIn("electricity", targetable_ids)
        self.assertNotIn("feedstock_quantity", targetable_ids)

    def test_legacy_first_class_key_is_migrated(self):
        # Externally-authored schemas may still carry the old `first_class` key;
        # it must load and behave as `search_targetable`.
        raw = load_fixture(TI)
        for p in raw["parameters"]:
            if "search_targetable" in p:
                p["first_class"] = p.pop("search_targetable")
        schema = Schema(raw)
        self.assertEqual(schema.report.errors, [])
        self.assertTrue(schema.is_search_targetable("electricity"))
        # The deprecated key is gone after migration.
        self.assertNotIn("first_class", schema.parameter("electricity"))

    def test_required_convention_files(self):
        self.assertEqual(
            self.ti.required_convention_files(),
            ["currency-rates.csv", "cepci.csv", "unit-conversions.csv", "scaling-exponents.csv"],
        )
        self.assertEqual(
            self.compute.required_convention_files(),
            ["currency-rates.csv", "cpi.csv", "unit-conversions.csv"],
        )

    def test_rubric_accessors(self):
        self.assertEqual(
            self.ti.rubric_dimensions,
            ["mechanism", "cost_driver", "scale", "temperature_atmosphere", "product_form_factor"],
        )
        self.assertTrue(self.ti.rubric_hard_rule)
        self.assertIsNone(self.compute.comparable_rubric)
        self.assertEqual(self.compute.rubric_dimensions, [])

    def test_entities_by_policy(self):
        self.assertEqual(self.ti.entities_by_policy("comparables_first"), ["1C", "4", "5", "6"])
        self.assertEqual(
            self.ti.entities_by_policy("first_principles_only"), ["1A", "1B", "2A", "2B"]
        )

    def test_defaults_and_fallbacks(self):
        self.assertEqual(self.ti.extraction_batch_size, 8)
        self.assertEqual(self.ti.master_list_candidate_cap, 15)
        self.assertEqual(self.ti.gap_fill_candidate_cap, 5)
        # compute declares no `defaults` block -> Vicky TEA fallbacks.
        self.assertEqual(self.compute.master_list_candidate_cap, 15)
        self.assertEqual(self.compute.gap_fill_candidate_cap, 5)
        self.assertEqual(self.compute.extraction_batch_size, 8)

    def test_vocabulary_labels(self):
        self.assertEqual(self.ti.entity_label, "process unit")
        self.assertEqual(self.ti.parameter_label, "field")
        self.assertEqual(self.compute.entity_label, "cost center")
        # No vocabulary block -> neutral fallback.
        bare = Schema({**load_fixture(TI), "vocabulary": {}})
        self.assertEqual(bare.label_for("entity"), "entity")


class JsonSchemaFileTests(unittest.TestCase):
    def test_json_schema_is_loadable(self):
        schema = load_json_schema()
        self.assertEqual(schema.get("type"), "object")
        self.assertIn("tea_id", schema.get("properties", {}))

    def test_jsonschema_accepts_fixtures_when_available(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = load_json_schema()
        jsonschema.validators.validator_for(schema).check_schema(schema)
        for name in (TI, COMPUTE):
            jsonschema.validate(load_fixture(name), schema)

    def test_jsonschema_rejects_bad_config_when_available(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = load_json_schema()
        bad = copy.deepcopy(load_fixture(TI))
        bad["basis"]["inflation_index"] = "RPI"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


if __name__ == "__main__":
    unittest.main()
