"""Tests for T7 estimation manifests, appends, source registration, and review.

Estimation now follows the single-anchor ladder: a backed estimate (quality tag
``E``) is built from exactly one real extracted anchor plus assumed constants and
a named enabling assumption; an unbacked estimate (quality tag ``U``, loop 3) is
a transparent estimate with no sourceable anchor, flagged loudly.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from append_estimation_rows import (  # noqa: E402
    EstimationValidationError,
    append_estimation_rows,
    validate_estimation_payload,
)
from apply_held_estimates import apply_held_estimates  # noqa: E402
from build_estimation_manifest import build_manifest  # noqa: E402
from lib.csvio import AUDIT_FIELDNAMES, MAIN_INPUT_FIELDNAMES, SOURCES_FIELDNAMES, read_rows, write_rows  # noqa: E402
from lib.schema import Schema  # noqa: E402
from sweep_held_estimates import HELD_ESTIMATES_FIELDNAMES, sweep_held_estimates  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMPUTE_SCHEMA = FIXTURES / "compute-service.tea-schema.json"
TI_SCHEMA = FIXTURES / "ti-6al-4v.tea-schema.json"


def audit_row(**updates):
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "entity": "compute_hardware",
            "parameter": "monthly_cost",
            "source_key": "real-source",
            "source_url": "https://example.test/real",
            "page_ref": "p. 1",
            "raw_value": "100",
            "raw_units": "USD/month",
            "raw_basis_year": "2025",
            "quality_tag": "A",
            "normalized_value": "100",
            "normalized_units": "USD/month",
            "relevance_status": "clear",
        }
    )
    row.update(updates)
    return row


def _anchor(source_key, source_url, value, units, access_notes=None):
    anchor = {
        "source_key": source_key,
        "source_url": source_url,
        "title": "Cost benchmark",
        "authors": "Example Analysts",
        "year": "2025",
        "publisher_or_journal": "Example Benchmarks",
        "value": value,
        "units": units,
        "page_ref": "Table 1",
        "page_or_table_reference": "Table 1",
        "quality_tag": "B",
    }
    if access_notes:
        anchor["access_notes"] = access_notes
    return anchor


def single_anchor_row(
    *,
    entity="compute_hardware",
    parameter="monthly_cost",
    source_key="gpu-cost-benchmark",
    source_url="https://example.test/gpu-cost",
    raw_value="100",
    raw_units="USD/month",
    access_notes=None,
    loop=1,
):
    anchor = _anchor(source_key, source_url, raw_value, raw_units, access_notes)
    return {
        "entity": entity,
        "parameter": parameter,
        "source_key": source_key,
        "source_url": source_url,
        "page_ref": "Table 1",
        "raw_value": raw_value,
        "raw_units": raw_units,
        "raw_basis_year": "2025",
        "quality_tag": "E",
        "relevance_status": "clear",
        "estimate_justification": {
            "method": "single_anchor",
            "loop": loop,
            "enabling_assumption": "The benchmarked service is similar enough to this cell.",
            "equation": f"{parameter} = anchor_value",
            "anchor": anchor,
            "assumed_constants": [],
            "derivation_steps": [
                "Read the anchor value from the cited table.",
                f"Final: {parameter} = {raw_value} {raw_units}.",
            ],
            "estimator_confidence": "medium",
            "caveats": ["Fixture estimate for pipeline tests."],
        },
    }


def unbacked_row(
    *,
    entity="compute_hardware",
    parameter="throughput",
    raw_value="2",
    raw_units="1M tokens/h",
):
    return {
        "entity": entity,
        "parameter": parameter,
        "source_key": "",
        "source_url": "",
        "page_ref": "n/a (unbacked estimate)",
        "raw_value": raw_value,
        "raw_units": raw_units,
        "raw_basis_year": "2025",
        "quality_tag": "U",
        "relevance_status": "clear",
        "estimate_justification": {
            "method": "unbacked",
            "loop": 3,
            "unbacked": True,
            "enabling_assumption": "No sourceable anchor exists; transparent engineering judgment only.",
            "equation": f"{parameter} = assumed typical value",
            "derivation_steps": [
                "Loops 1-2 found no sourceable anchor.",
                f"Assume {parameter} = {raw_value} {raw_units}.",
            ],
            "estimator_confidence": "low",
            "caveats": ["Unbacked estimate; verify before relying on it."],
        },
    }


class AutoEstimationAccessTests(unittest.TestCase):
    def test_auto_estimates_require_open_access_anchor(self):
        data = json.loads(COMPUTE_SCHEMA.read_text(encoding="utf-8"))
        data["execution_mode"] = "auto"
        schema = Schema(data)
        row = single_anchor_row()
        payload = {"schema_tea_id": schema.tea_id, "force_refresh": False, "rows": [row]}

        with self.assertRaises(EstimationValidationError) as ctx:
            validate_estimation_payload(payload, schema)
        self.assertIn("open/public full-text access", str(ctx.exception))

        row["estimate_justification"]["anchor"]["access_notes"] = "open access full text verified"
        validate_estimation_payload(payload, schema)


class EstimationManifestTests(unittest.TestCase):
    def test_manifest_lists_blank_cells_and_respects_prior_estimate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            write_rows(
                audit,
                AUDIT_FIELDNAMES,
                [
                    audit_row(selected_for_model="TRUE"),
                    # an unbacked (U) prior estimate also counts as already-estimated
                    audit_row(
                        parameter="power_draw",
                        source_key="",
                        quality_tag="U",
                        normalized_value="4",
                        normalized_units="kWh/1M tokens",
                        selected_for_model="",
                    ),
                ],
            )

            manifest = build_manifest(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=None,
            )
            compute = [
                entity for entity in manifest["entities"]
                if entity["entity"] == "compute_hardware"
            ][0]
            blanks = {param["id"] for param in compute["blank_parameters"]}
            self.assertNotIn("monthly_cost", blanks)
            self.assertNotIn("power_draw", blanks)  # U counts as already estimated
            self.assertIn("throughput", blanks)

            refreshed = build_manifest(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=None,
                force_refresh=True,
            )
            refreshed_compute = [
                entity for entity in refreshed["entities"]
                if entity["entity"] == "compute_hardware"
            ][0]
            refreshed_blanks = {param["id"] for param in refreshed_compute["blank_parameters"]}
            self.assertIn("power_draw", refreshed_blanks)  # force-refresh re-opens the U cell
            self.assertNotIn("monthly_cost", refreshed_blanks)

    def test_manifest_carries_comparable_rubric_from_schema(self):
        manifest = build_manifest(
            schema_path=TI_SCHEMA,
            audit_path=Path("missing-audit.csv"),
            main_input_path=None,
        )
        self.assertEqual(
            manifest["comparable_rubric"]["dimensions"],
            ["mechanism", "cost_driver", "scale", "temperature_atmosphere", "product_form_factor"],
        )
        one_c = [entity for entity in manifest["entities"] if entity["entity"] == "1C"][0]
        self.assertTrue(any(param["id"] == "specific_capex" for param in one_c["blank_parameters"]))

    def test_manifest_skips_cells_marked_shared_in_main_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            main = root / "Main Input.csv"
            write_rows(audit, AUDIT_FIELDNAMES, [])
            row = {name: "" for name in MAIN_INPUT_FIELDNAMES}
            row.update({"entity": "compute_hardware", "parameter": "monthly_cost", "input_origin": "shared"})
            write_rows(main, MAIN_INPUT_FIELDNAMES, [row])

            manifest = build_manifest(
                schema_path=COMPUTE_SCHEMA,
                audit_path=audit,
                main_input_path=main,
            )
            compute = [
                entity for entity in manifest["entities"]
                if entity["entity"] == "compute_hardware"
            ][0]
            blanks = {param["id"] for param in compute["blank_parameters"]}
            self.assertNotIn("monthly_cost", blanks)


class AppendEstimationRowsTests(unittest.TestCase):
    def test_append_registers_anchor_source_and_audit_source_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            sources = root / "Sources.csv"
            payload = root / "estimation_output.json"
            write_rows(audit, AUDIT_FIELDNAMES, [])
            write_rows(sources, SOURCES_FIELDNAMES, [])
            payload.write_text(
                json.dumps(
                    {
                        "schema_tea_id": "compute-service-inference",
                        "force_refresh": False,
                        "rows": [single_anchor_row()],
                    }
                ),
                encoding="utf-8",
            )

            result = append_estimation_rows(
                schema_path=COMPUTE_SCHEMA,
                input_path=payload,
                audit_path=audit,
                sources_path=sources,
            )

            self.assertEqual(len(result["rows_appended"]), 1)
            source_rows = read_rows(sources)
            self.assertEqual(source_rows[0]["source_key"], "gpu-cost-benchmark")
            self.assertEqual(source_rows[0]["source_role"], "estimate")
            self.assertEqual(source_rows[0]["source_url"], "https://example.test/gpu-cost")
            audit_rows = read_rows(audit)
            self.assertEqual(audit_rows[0]["quality_tag"], "E")
            self.assertEqual(audit_rows[0]["source_url"], "https://example.test/gpu-cost")
            self.assertEqual(json.loads(audit_rows[0]["estimate_justification"])["method"], "single_anchor")

            rerun = append_estimation_rows(
                schema_path=COMPUTE_SCHEMA,
                input_path=payload,
                audit_path=audit,
                sources_path=sources,
            )
            self.assertEqual(len(rerun["rows_appended"]), 0)
            self.assertEqual(rerun["skipped_existing_e"], [("compute_hardware", "monthly_cost")])
            self.assertEqual(len(read_rows(audit)), 1)

    def test_unbacked_row_appends_with_u_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            sources = root / "Sources.csv"
            payload = root / "estimation_output.json"
            write_rows(audit, AUDIT_FIELDNAMES, [])
            write_rows(sources, SOURCES_FIELDNAMES, [])
            payload.write_text(
                json.dumps({"force_refresh": False, "rows": [unbacked_row()]}),
                encoding="utf-8",
            )
            result = append_estimation_rows(
                schema_path=COMPUTE_SCHEMA,
                input_path=payload,
                audit_path=audit,
                sources_path=sources,
            )
            self.assertEqual(len(result["rows_appended"]), 1)
            # an unbacked estimate registers no anchor source
            self.assertEqual(len(read_rows(sources)), 0)
            row = read_rows(audit)[0]
            self.assertEqual(row["quality_tag"], "U")
            self.assertEqual(json.loads(row["estimate_justification"])["method"], "unbacked")

    def test_single_anchor_requires_real_anchor_provenance(self):
        schema = Schema(json.loads(COMPUTE_SCHEMA.read_text(encoding="utf-8")))
        row = single_anchor_row()
        # an estimate-tagged anchor is not real extraction provenance
        row["estimate_justification"]["anchor"]["quality_tag"] = "E"
        payload = {"force_refresh": False, "rows": [row]}
        with self.assertRaises(EstimationValidationError) as ctx:
            validate_estimation_payload(payload, schema)
        self.assertIn("real extraction tag", str(ctx.exception))

    def test_existing_extraction_source_role_upgrades_to_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            sources = root / "Sources.csv"
            payload = root / "estimation_output.json"
            write_rows(audit, AUDIT_FIELDNAMES, [])
            write_rows(
                sources,
                SOURCES_FIELDNAMES,
                [
                    {
                        "source_key": "gpu-cost-benchmark",
                        "source_url": "https://example.test/gpu-cost",
                        "source_role": "extraction",
                    }
                ],
            )
            payload.write_text(
                json.dumps({"force_refresh": False, "rows": [single_anchor_row()]}),
                encoding="utf-8",
            )

            append_estimation_rows(
                schema_path=COMPUTE_SCHEMA,
                input_path=payload,
                audit_path=audit,
                sources_path=sources,
            )
            self.assertEqual(read_rows(sources)[0]["source_role"], "both")


class HeldEstimateReviewTests(unittest.TestCase):
    def test_sweep_and_apply_accept_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            sources = root / "Sources.csv"
            payload = root / "estimation_output.json"
            queue = root / "held_estimates.csv"
            write_rows(audit, AUDIT_FIELDNAMES, [])
            write_rows(sources, SOURCES_FIELDNAMES, [])
            payload.write_text(
                json.dumps({"force_refresh": False, "rows": [single_anchor_row()]}),
                encoding="utf-8",
            )
            append_estimation_rows(
                schema_path=COMPUTE_SCHEMA,
                input_path=payload,
                audit_path=audit,
                sources_path=sources,
            )

            swept = sweep_held_estimates(audit_path=audit, output_path=queue, sources_path=sources)
            self.assertEqual(len(swept["rows"]), 1)
            queued = read_rows(queue)
            self.assertEqual(queued[0]["source_url"], "https://example.test/gpu-cost")
            self.assertIn("method=single_anchor", queued[0]["notes"])
            queued[0]["proposed_verdict"] = "accept"
            queued[0]["analyst_answer"] = "Reasonable as an E-quality placeholder."
            write_rows(queue, HELD_ESTIMATES_FIELDNAMES, queued)

            result = apply_held_estimates(audit_path=audit, queue_path=queue)
            self.assertEqual(result["counts"]["accept"], 1)
            row = read_rows(audit)[0]
            self.assertEqual(row["quality_tag"], "E")
            self.assertEqual(row["held_estimate_status"], "clear")
            self.assertIn("Reasonable", row["held_estimate_answer"])

    def test_sweep_flags_unbacked_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            queue = root / "held_estimates.csv"
            row = unbacked_row()
            audit_estimate = audit_row(
                parameter="throughput",
                source_key="",
                source_url="",
                raw_value="2",
                raw_units="1M tokens/h",
                quality_tag="U",
                normalized_value="2",
                normalized_units="1M tokens/h",
                estimate_justification=json.dumps(row["estimate_justification"]),
            )
            write_rows(audit, AUDIT_FIELDNAMES, [audit_estimate])
            sweep_held_estimates(audit_path=audit, output_path=queue, sources_path=None)
            queued = read_rows(queue)
            self.assertEqual(len(queued), 1)
            self.assertIn("UNBACKED ESTIMATE", queued[0]["notes"])

    def test_analyst_override_retags_to_d(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "Audit.csv"
            queue = root / "held_estimates.csv"
            row = single_anchor_row(
                parameter="throughput",
                source_key="throughput-benchmark",
                source_url="https://example.test/throughput",
                raw_value="2",
                raw_units="1M tokens/h",
            )
            audit_estimate = audit_row(
                parameter="throughput",
                source_key="throughput-benchmark",
                source_url="https://example.test/throughput",
                raw_value="2",
                raw_units="1M tokens/h",
                quality_tag="E",
                normalized_value="2",
                normalized_units="1M tokens/h",
                estimate_justification=json.dumps(row["estimate_justification"]),
            )
            write_rows(audit, AUDIT_FIELDNAMES, [audit_estimate])

            sweep_held_estimates(audit_path=audit, output_path=queue, sources_path=None)
            queued = read_rows(queue)
            queued[0]["proposed_verdict"] = "analyst-override"
            queued[0]["analyst_value"] = "1.5"
            queued[0]["analyst_units"] = "1M tokens/h"
            queued[0]["analyst_answer"] = "Use internal fleet benchmark instead."
            write_rows(queue, HELD_ESTIMATES_FIELDNAMES, queued)

            result = apply_held_estimates(audit_path=audit, queue_path=queue)
            self.assertEqual(result["counts"]["analyst-override"], 1)
            updated = read_rows(audit)[0]
            self.assertEqual(updated["quality_tag"], "D")
            self.assertEqual(updated["normalized_value"], "1.5")
            self.assertEqual(updated["held_estimate_status"], "clear")
            self.assertIn("internal fleet", updated["transform_steps"])


if __name__ == "__main__":
    unittest.main()
