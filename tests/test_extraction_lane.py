"""Tests for T4 extraction prompts, manifests, ingest, and hold resolution."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from apply_held_verdicts import apply_verdicts  # noqa: E402
from extraction_manifest import build_manifest, write_manifest  # noqa: E402
from ingest_extractor_output import ingest_extractor_output  # noqa: E402
from lib.csvio import AUDIT_FIELDNAMES, CSV_SCHEMAS, SOURCES_FIELDNAMES, column_names, read_rows, write_rows  # noqa: E402
from lib.extraction import ExtractionHoldError, ExtractionValidationError, assert_no_unresolved_holds  # noqa: E402
from lib.source_url import SourceUrlError  # noqa: E402
from next_batch import next_batch  # noqa: E402
from sweep_held_questions import sweep_held_questions  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
TI_SCHEMA = FIXTURES / "ti-6al-4v.tea-schema.json"
HELD_FIELDNAMES = column_names(CSV_SCHEMAS["held_questions.csv"])


def candidate_doc(source_key="useful-source"):
    return {
        "schema_tea_id": "ti-6al-4v-incumbent",
        "candidates": [
            {
                "source_key": source_key,
                "title": "Useful Source",
                "authors": "Example Institute",
                "year": 2024,
                "publisher_or_journal": "Example Reports",
                "source_url": "https://example.test/report",
                "quality_estimate": "B",
                "field_coverage": [
                    {"entity": "1A", "parameters": ["electricity", "thermal_energy"]}
                ],
            }
        ],
    }


def sources_rows(source_key="useful-source"):
    return [
        {
            "source_key": source_key,
            "title": "Useful Source",
            "authors": "Example Institute",
            "year": "2024",
            "publisher_or_journal": "Example Reports",
            "source_url": "https://example.test/report",
            "source_role": "extraction",
            "notes": "search_quality_estimate=B",
        }
    ]


def clear_extractor_doc():
    return {
        "source_key": "useful-source",
        "source_url": "https://example.test/report",
        "extracted_rows": [
            {
                "entity": "1A",
                "parameter": "electricity",
                "source_key": "useful-source",
                "source_url": "https://example.test/report",
                "page_ref": "Table 2, p. 14",
                "raw_value": "12.4",
                "raw_units": "kWh/kg TiCl4",
                "raw_basis_scale": None,
                "raw_basis_scale_units": None,
                "raw_basis_year": "2022",
                "quality_tag": "B",
                "relevance_status": "clear",
                "analyst_question": None,
                "extractor_notes": "Explicitly attributed to the in-scope fluidized-bed chlorination process.",
            }
        ],
        "extraction_summary": {},
    }


def hold_audit_row():
    row = {name: "" for name in AUDIT_FIELDNAMES}
    row.update(
        {
            "entity": "1A",
            "parameter": "electricity",
            "source_key": "useful-source",
            "source_url": "https://example.test/report",
            "page_ref": "Table 2, p. 14",
            "raw_value": "12.4",
            "raw_units": "kWh/kg TiCl4",
            "raw_basis_year": "2022",
            "quality_tag": "B",
            "relevance_status": "hold",
            "analyst_question": "Table 2 says 12.4 kWh/kg on p. 14 in a row labeled baseline; is this the incumbent chlorination route? Leaning yes.",
            "extractor_notes": "Captured pending scope confirmation.",
        }
    )
    return row


class ExtractionManifestTests(unittest.TestCase):
    def test_manifest_joins_registered_sources_to_schema_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            search_json = tmp_path / "master-list.json"
            search_json.write_text(json.dumps(candidate_doc()), encoding="utf-8")
            sources = tmp_path / "Sources.csv"
            write_rows(sources, SOURCES_FIELDNAMES, sources_rows())
            source_dir = tmp_path / "master list sources"
            source_dir.mkdir()
            (source_dir / "1A_useful-source.pdf").write_text("downloaded", encoding="utf-8")

            manifest = build_manifest(
                schema_path=TI_SCHEMA,
                inputs=[search_json],
                sources_path=sources,
                source_dirs=[source_dir],
                output_dir=tmp_path / "extractions",
            )

            self.assertEqual(manifest["count"], 1)
            entry = manifest["manifest"][0]
            self.assertEqual(entry["source_key"], "useful-source")
            self.assertEqual(entry["source_url"], "https://example.test/report")
            self.assertEqual(entry["source_quality_estimate"], "B")
            self.assertEqual(entry["coverage_targets"][0]["entity"], "1A")
            self.assertIn("scope_frame", entry["coverage_targets"][0])
            params = [p["id"] for p in entry["coverage_targets"][0]["parameters"]]
            self.assertEqual(params, ["electricity", "thermal_energy"])

    def test_next_batch_skips_nonempty_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "done.json"
            manifest_path = tmp_path / "manifest.json"
            write_manifest(
                manifest_path,
                {
                    "manifest": [
                        {"id": "done", "output_json": str(out)},
                        {"id": "pending", "output_json": str(tmp_path / "pending.json")},
                    ]
                },
            )
            out.write_text("{}", encoding="utf-8")

            batch = next_batch(manifest_path, batch_size=8)
            self.assertEqual([entry["id"] for entry in batch], ["pending"])


class ExtractionIngestTests(unittest.TestCase):
    def test_ingest_validates_and_appends_audit_rows_with_source_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sources = tmp_path / "Sources.csv"
            audit = tmp_path / "Audit.csv"
            doc_path = tmp_path / "extractor.json"
            write_rows(sources, SOURCES_FIELDNAMES, sources_rows())
            write_rows(audit, AUDIT_FIELDNAMES, [])
            doc_path.write_text(json.dumps(clear_extractor_doc()), encoding="utf-8")

            result = ingest_extractor_output(
                schema_path=TI_SCHEMA,
                input_path=doc_path,
                audit_path=audit,
                sources_path=sources,
            )

            self.assertEqual(result["counts"]["rows"], 1)
            rows = read_rows(audit)
            self.assertEqual(rows[0]["entity"], "1A")
            self.assertEqual(rows[0]["parameter"], "electricity")
            self.assertEqual(rows[0]["source_url"], "https://example.test/report")
            self.assertEqual(rows[0]["relevance_status"], "clear")

    def test_ingest_rejects_hold_without_question_and_wrong_source_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sources = tmp_path / "Sources.csv"
            audit = tmp_path / "Audit.csv"
            write_rows(sources, SOURCES_FIELDNAMES, sources_rows())
            write_rows(audit, AUDIT_FIELDNAMES, [])

            bad_hold = clear_extractor_doc()
            bad_hold["extracted_rows"][0]["relevance_status"] = "hold"
            bad_hold["extracted_rows"][0]["analyst_question"] = None
            bad_path = tmp_path / "bad-hold.json"
            bad_path.write_text(json.dumps(bad_hold), encoding="utf-8")
            with self.assertRaises(ExtractionValidationError):
                ingest_extractor_output(
                    schema_path=TI_SCHEMA,
                    input_path=bad_path,
                    audit_path=audit,
                    sources_path=sources,
                )

            mismatch = clear_extractor_doc()
            mismatch["source_url"] = "https://wrong.test/report"
            mismatch_path = tmp_path / "mismatch.json"
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaises(SourceUrlError):
                ingest_extractor_output(
                    schema_path=TI_SCHEMA,
                    input_path=mismatch_path,
                    audit_path=audit,
                    sources_path=sources,
                )

    def test_ingest_can_require_manifest_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sources = tmp_path / "Sources.csv"
            audit = tmp_path / "Audit.csv"
            doc_path = tmp_path / "extractor.json"
            write_rows(sources, SOURCES_FIELDNAMES, sources_rows())
            write_rows(audit, AUDIT_FIELDNAMES, [])
            doc_path.write_text(json.dumps(clear_extractor_doc()), encoding="utf-8")

            with self.assertRaises(ExtractionValidationError):
                ingest_extractor_output(
                    schema_path=TI_SCHEMA,
                    input_path=doc_path,
                    audit_path=audit,
                    sources_path=sources,
                    expected_targets=[("1A", "electricity"), ("1A", "thermal_energy")],
                )

    def test_ti_run2_slice_ingests_equivalent_neutral_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_key = "yang-rutile-carbon-fluidized-chlorination-2022"
            source_url = "https://www.sciencedirect.com/science/article/pii/S2238785422003039"
            sources = tmp_path / "Sources.csv"
            audit = tmp_path / "Audit.csv"
            doc_path = tmp_path / "run2-slice.json"
            write_rows(
                sources,
                SOURCES_FIELDNAMES,
                [
                    {
                        "source_key": source_key,
                        "authors": "Fan Yang et al.",
                        "title": "Study on reaction behaviors and mechanisms of rutile TiO2",
                        "year": "2022",
                        "publisher_or_journal": "Journal of Materials Research and Technology",
                        "source_url": source_url,
                        "source_role": "extraction",
                    }
                ],
            )
            write_rows(audit, AUDIT_FIELDNAMES, [])
            doc_path.write_text(
                json.dumps(
                    {
                        "source_key": source_key,
                        "source_url": source_url,
                        "extracted_rows": [
                            {
                                "entity": "1A",
                                "parameter": "Ti_yield",
                                "source_key": source_key,
                                "source_url": source_url,
                                "page_ref": "Section 3.2 and Fig. 8, p.1209; Conclusions, p.1215",
                                "raw_value": "79.52%",
                                "raw_units": "chlorination rate",
                                "raw_basis_scale": None,
                                "raw_basis_scale_units": None,
                                "raw_basis_year": 2022,
                                "quality_tag": "A",
                                "relevance_status": "clear",
                                "analyst_question": None,
                                "extractor_notes": "Affirmed to fluidized carbochlorination of rutile with petroleum coke and Cl2.",
                            }
                        ],
                        "extraction_summary": {"rows_with_values": 1},
                    }
                ),
                encoding="utf-8",
            )

            ingest_extractor_output(
                schema_path=TI_SCHEMA,
                input_path=doc_path,
                audit_path=audit,
                sources_path=sources,
                expected_targets=[("1A", "Ti_yield")],
            )

            row = read_rows(audit)[0]
            self.assertEqual(row["entity"], "1A")
            self.assertEqual(row["parameter"], "Ti_yield")
            self.assertEqual(row["raw_value"], "79.52%")
            self.assertEqual(row["raw_units"], "chlorination rate")
            self.assertEqual(row["source_url"], source_url)


class HeldQuestionTests(unittest.TestCase):
    def test_sweep_apply_accept_resolves_hold_and_hard_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            audit = tmp_path / "Audit.csv"
            queue = tmp_path / "held_questions.csv"
            write_rows(audit, AUDIT_FIELDNAMES, [hold_audit_row()])

            with self.assertRaises(ExtractionHoldError):
                assert_no_unresolved_holds(audit)

            result = sweep_held_questions(audit_path=audit, output_path=queue)
            self.assertEqual(len(result["rows"]), 1)
            queued = read_rows(queue)
            self.assertEqual(queued[0]["source_url"], "https://example.test/report")
            queued[0]["proposed_verdict"] = "accept"
            queued[0]["analyst_answer"] = "Yes, the table is explicitly the incumbent baseline."
            write_rows(queue, HELD_FIELDNAMES, queued)

            applied = apply_verdicts(audit_path=audit, queue_path=queue)
            self.assertEqual(applied["counts"]["accept"], 1)
            row = read_rows(audit)[0]
            self.assertEqual(row["relevance_status"], "clear")
            self.assertEqual(row["raw_value"], "12.4")
            self.assertEqual(row["analyst_question"], "")
            assert_no_unresolved_holds(audit)

    def test_apply_reject_blanks_captured_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            audit = tmp_path / "Audit.csv"
            queue = tmp_path / "held_questions.csv"
            write_rows(audit, AUDIT_FIELDNAMES, [hold_audit_row()])
            sweep_held_questions(audit_path=audit, output_path=queue)
            queued = read_rows(queue)
            queued[0]["proposed_verdict"] = "reject"
            queued[0]["analyst_answer"] = "This row is the plasma alternate."
            write_rows(queue, HELD_FIELDNAMES, queued)

            applied = apply_verdicts(audit_path=audit, queue_path=queue)
            self.assertEqual(applied["counts"]["reject"], 1)
            row = read_rows(audit)[0]
            self.assertEqual(row["relevance_status"], "reject")
            self.assertEqual(row["raw_value"], "")
            self.assertEqual(row["page_ref"], "")
            self.assertEqual(row["quality_tag"], "")


if __name__ == "__main__":
    unittest.main()
