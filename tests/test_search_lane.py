"""Tests for T3 search prompts, candidate validation, and source registration."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib.csvio import SOURCES_FIELDNAMES, read_rows, write_rows  # noqa: E402
from lib.schema import GLOBAL_ENTITY_ID, Schema, load_schema  # noqa: E402
from lib.search import SearchValidationError, validate_search_doc  # noqa: E402
from register_sources import register_sources  # noqa: E402
from rename_sources import rename_sources  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"
TI_SCHEMA = FIXTURES / "ti-6al-4v.tea-schema.json"


def candidate(source_key="useful-source", *, coverage=None, source_url="https://example.test/report"):
    return {
        "source_key": source_key,
        "title": "Useful Source",
        "authors": "Example Institute",
        "year": 2024,
        "publisher_or_journal": "Example Reports",
        "source_url": source_url,
        "doi": "",
        "quality_estimate": "B",
        "access_notes": "open access",
        "field_coverage": coverage or [{"entity": "1A", "parameters": ["electricity"]}],
        "rationale": "Expected to report the covered parameter at the right boundary.",
    }


class SearchCandidateValidationTests(unittest.TestCase):
    def test_auto_mode_requires_explicit_open_access(self):
        data = json.loads(TI_SCHEMA.read_text(encoding="utf-8"))
        data["execution_mode"] = "auto"
        schema = Schema(data)
        restricted = candidate()
        restricted["access_notes"] = "paywall (publisher)"
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(
                {"schema_tea_id": schema.tea_id, "candidates": [restricted]},
                schema,
            )
        self.assertIn("open-access", str(ctx.exception))

        accessible = candidate()
        accessible["access_notes"] = "open access full text verified"
        self.assertEqual(
            len(
                validate_search_doc(
                    {"schema_tea_id": schema.tea_id, "candidates": [accessible]},
                    schema,
                )
            ),
            1,
        )

    def test_master_candidate_coverage_must_resolve_to_schema_pairs(self):
        schema = load_schema(TI_SCHEMA)
        valid_doc = {
            "schema_tea_id": schema.tea_id,
            "reference_value_subqueries": [
                {
                    "parameter": "electricity_price",
                    "query": "US industrial electricity price USD per kWh EIA 2025",
                    "rationale": "Public utility price series.",
                }
            ],
            "candidates": [
                candidate(
                    coverage=[
                        {"entity": "1A", "parameters": ["electricity"]},
                        {"entity": GLOBAL_ENTITY_ID, "parameters": ["electricity_price"]},
                    ]
                )
            ],
        }
        self.assertEqual(len(validate_search_doc(valid_doc, schema)), 1)

        invalid_doc = {
            "schema_tea_id": schema.tea_id,
            "candidates": [
                candidate(coverage=[{"entity": "1A", "parameters": ["Mg_recovery"]}])
            ],
        }
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(invalid_doc, schema)
        self.assertIn("does not apply", str(ctx.exception))

    def test_context_free_reference_queries_reject_tea_context(self):
        schema = load_schema(TI_SCHEMA)
        doc = {
            "schema_tea_id": schema.tea_id,
            "reference_value_subqueries": [
                {
                    "parameter": "electricity_price",
                    "query": "Ti-6Al-4V Incumbent Chain industrial electricity price",
                    "rationale": "Bad query because it includes the system context.",
                }
            ],
            "candidates": [candidate()],
        }
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(doc, schema)
        self.assertIn("context-free", str(ctx.exception))

    def test_satisfied_cells_are_not_valid_search_coverage(self):
        schema = load_schema(TI_SCHEMA)
        doc = {
            "schema_tea_id": schema.tea_id,
            "candidates": [candidate()],
        }
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(doc, schema, satisfied_cells=[("1A", "electricity")])
        self.assertIn("satisfied shared inputs must be skipped", str(ctx.exception))

    def test_gap_fill_requires_search_targetable_coverage_from_config(self):
        schema = load_schema(TI_SCHEMA)
        non_targetable_only = {
            "schema_tea_id": schema.tea_id,
            "entity": "1A",
            "candidates": [
                candidate(coverage=[{"entity": "1A", "parameters": ["feedstock_quantity"]}])
            ],
        }
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(
                non_targetable_only,
                schema,
                mode="gap",
                entity_id="1A",
                uncovered_parameters=["feedstock_quantity"],
            )
        self.assertIn("search_targetable", str(ctx.exception))

        search_targetable_doc = {
            "schema_tea_id": schema.tea_id,
            "entity": "1A",
            "candidates": [
                candidate(coverage=[{"entity": "1A", "parameters": ["electricity"]}])
            ],
        }
        self.assertEqual(
            len(
                validate_search_doc(
                    search_targetable_doc,
                    schema,
                    mode="gap",
                    entity_id="1A",
                    uncovered_parameters=["electricity"],
                )
            ),
            1,
        )

    def test_gap_fill_rejects_doi_resolver_urls(self):
        schema = load_schema(TI_SCHEMA)
        doc = {
            "schema_tea_id": schema.tea_id,
            "entity": "1A",
            "candidates": [
                candidate(source_url="https://doi.org/10.1234/example")
            ],
        }
        with self.assertRaises(SearchValidationError) as ctx:
            validate_search_doc(
                doc,
                schema,
                mode="gap",
                entity_id="1A",
                uncovered_parameters=["electricity"],
            )
        self.assertIn("DOI resolver", str(ctx.exception))


class SearchSourceScriptTests(unittest.TestCase):
    def test_register_sources_appends_only_approved_files_with_source_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "master list sources"
            source_dir.mkdir()
            (source_dir / "1A_useful-source.pdf").write_text("downloaded", encoding="utf-8")

            search_json = tmp_path / "master-list.json"
            search_json.write_text(
                json.dumps({"schema_tea_id": "ti-6al-4v-incumbent", "candidates": [candidate()]}),
                encoding="utf-8",
            )
            sources = tmp_path / "Sources.csv"
            write_rows(sources, SOURCES_FIELDNAMES, [])

            result = register_sources(
                schema_path=TI_SCHEMA,
                input_path=search_json,
                source_dir=source_dir,
                sources_path=sources,
                access_date="2026-06-06",
            )

            self.assertEqual(len(result["rows"]), 1)
            rows = read_rows(sources)
            self.assertEqual(rows[0]["source_key"], "useful-source")
            self.assertEqual(rows[0]["source_url"], "https://example.test/report")
            self.assertEqual(rows[0]["source_role"], "extraction")

    def test_rename_sources_uses_entity_or_chain_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "gap fill sources"
            source_dir.mkdir()
            original = source_dir / "download_useful-source.pdf"
            original.write_text("not a real pdf but enough for filename matching", encoding="utf-8")

            search_json = tmp_path / "gap-fill.json"
            search_json.write_text(
                json.dumps({"schema_tea_id": "ti-6al-4v-incumbent", "entity": "1A", "candidates": [candidate()]}),
                encoding="utf-8",
            )

            result = rename_sources(
                schema_path=TI_SCHEMA,
                input_path=search_json,
                source_dir=source_dir,
                mode="gap",
                entity_id="1A",
                uncovered_parameters=["electricity"],
                apply=True,
                min_score=1,
            )

            self.assertEqual(len(result["selected"]), 1)
            self.assertFalse(original.exists())
            self.assertTrue((source_dir / "1A_useful-source.pdf").exists())


if __name__ == "__main__":
    unittest.main()
