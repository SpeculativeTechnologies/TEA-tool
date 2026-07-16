"""Tests for the anti-shortcut sub-agent spawn harness (workflow note #4)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrator as orch  # noqa: E402
from lib import orchestrator_state as st  # noqa: E402
from lib import spawn_harness  # noqa: E402

DATE = "2026-06-26"


def _init_run(tmp: str) -> Path:
    runs = Path(tmp) / "runs"
    orch.cmd_init(name="Harness Run", runs_dir=runs, today=DATE)
    return runs / "harness-run"


def _init_comparison(tmp: str) -> Path:
    runs = Path(tmp) / "runs"
    orch.cmd_init(
        name="Harness Comparison",
        runs_dir=runs,
        today=DATE,
        project_type="comparison",
        options=["lettuce:Lettuce", "rice:Rice"],
    )
    return runs / "harness-comparison"


def _write_extraction_manifest(run_dir: Path, ids: list[str]) -> None:
    manifest = {
        "schema_tea_id": "demo",
        "manifest": [
            {
                "id": entry_id,
                "source_key": entry_id,
                "output_json": f"extractions/{entry_id}.extraction.json",
            }
            for entry_id in ids
        ],
        "count": len(ids),
    }
    path = run_dir / "extractions" / "extraction_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _write_extraction_output(run_dir: Path, entry_id: str) -> None:
    path = run_dir / "extractions" / f"{entry_id}.extraction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source_key": entry_id, "extracted_rows": []}), encoding="utf-8")


def _write_estimation_manifest(run_dir: Path, entities: list[str]) -> None:
    path = run_dir / "estimation_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "entities": [
                    {"entity": entity, "blank_parameters": ["missing"]}
                    for entity in entities
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_master_search(run_dir: Path, *, gaps: list[str] | None = None) -> None:
    path = run_dir / "search-history" / "master-list.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_tea_id": "demo",
                "candidates": [],
                "coverage_summary": {
                    "parameters_likely_to_need_gap_fill": [
                        {"entity": entity, "parameters": ["missing"]}
                        for entity in (gaps or [])
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def _write_gap_search(run_dir: Path, entity: str) -> None:
    path = run_dir / "search-history" / f"gap-fill-{entity}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entity": entity, "candidates": []}), encoding="utf-8")


def _set_stage_direct(run_dir: Path, stage: str) -> None:
    state = st.read_state(run_dir)
    state["stage"] = stage
    st.write_state(run_dir, state)


class RequirementsTests(unittest.TestCase):
    def test_extraction_requirements_derived_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a", "src-b", "src-c"])
            spec = spawn_harness.stage_requirements(run_dir, "extraction")
            self.assertTrue(spec["computable"])
            self.assertEqual(len(spec["requirements"]), 3)
            self.assertEqual(
                {r["unit"] for r in spec["requirements"]}, {"src-a", "src-b", "src-c"}
            )

    def test_missing_manifest_is_a_blocking_contract_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            spec = spawn_harness.stage_requirements(run_dir, "extraction")
            self.assertTrue(spec["computable"])
            self.assertTrue(spec["contract_problems"])
            report = spawn_harness.verify_stage(run_dir, "extraction", st.read_state(run_dir))
            self.assertTrue(report["blocking"])

    def test_estimation_manifest_is_also_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            report = spawn_harness.verify_stage(run_dir, "estimation", st.read_state(run_dir))
            self.assertTrue(report["blocking"])
            self.assertIn("estimation_manifest.json", report["contract_problems"][0])

    def test_evidence_collection_requires_master_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            spec = spawn_harness.stage_requirements(run_dir, "evidence_collection")
            self.assertEqual(spec["requirements"][0]["unit"], "master-list")
            self.assertEqual(
                spec["requirements"][0]["artifact"], "search-history\\master-list.json"
            )

    def test_master_search_declared_gaps_require_targeted_searches(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_master_search(run_dir, gaps=["growth", "REF"])
            units = {
                req["unit"]
                for req in spawn_harness.stage_requirements(run_dir, "evidence_collection")[
                    "requirements"
                ]
            }
            self.assertEqual(units, {"master-list", "gap-fill:growth", "gap-fill:REF"})

    def test_comparison_requires_master_search_for_every_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_comparison(tmp)
            requirements = spawn_harness.stage_requirements(
                run_dir, "evidence_collection"
            )["requirements"]
            self.assertEqual(
                {req["unit"] for req in requirements},
                {"master-list:lettuce", "master-list:rice"},
            )
            self.assertEqual(
                {req["artifact"] for req in requirements},
                {
                    "options\\lettuce\\search-history\\master-list.json",
                    "options\\rice\\search-history\\master-list.json",
                },
            )

    def test_comparison_derives_extraction_units_from_every_option_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_comparison(tmp)
            for option in ("lettuce", "rice"):
                _write_extraction_manifest(run_dir / "options" / option, ["source-a"])
            spec = spawn_harness.stage_requirements(run_dir, "extraction")
            self.assertFalse(spec["contract_problems"])
            self.assertEqual(
                {req["unit"] for req in spec["requirements"]},
                {"lettuce:source-a", "rice:source-a"},
            )
            self.assertEqual(
                {req["artifact"] for req in spec["requirements"]},
                {
                    "options\\lettuce\\extractions\\source-a.extraction.json",
                    "options\\rice\\extractions\\source-a.extraction.json",
                },
            )

    def test_comparison_derives_estimation_units_from_every_option_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_comparison(tmp)
            _write_estimation_manifest(run_dir / "options" / "lettuce", ["growth"])
            _write_estimation_manifest(run_dir / "options" / "rice", [])
            spec = spawn_harness.stage_requirements(run_dir, "estimation")
            self.assertFalse(spec["contract_problems"])
            self.assertEqual(
                {req["unit"] for req in spec["requirements"]}, {"lettuce:growth"}
            )

    def test_fixed_quality_review_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            for stage in ("completeness_review", "finalization"):
                spec = spawn_harness.stage_requirements(run_dir, stage)
                self.assertTrue(spec["computable"])
                self.assertEqual(len(spec["requirements"]), 1)
                self.assertEqual(spec["requirements"][0]["agent_type"], spawn_harness.QUALITY_REVIEWER)


class VerifyTests(unittest.TestCase):
    def test_missing_spawns_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a", "src-b"])
            state = st.read_state(run_dir)
            report = spawn_harness.verify_stage(run_dir, "extraction", state)
            self.assertFalse(report["reconciled"])
            self.assertTrue(report["blocking"])
            self.assertEqual(len(report["missing"]), 2)

    def test_completed_with_artifacts_reconciles(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a", "src-b"])
            _set_stage_direct(run_dir, "extraction")
            for entry_id in ("src-a", "src-b"):
                _write_extraction_output(run_dir, entry_id)
                orch.cmd_record_spawn(
                    run_dir,
                    stage="extraction",
                    agent_type=spawn_harness.SOURCE_EXTRACTOR,
                    unit=entry_id,
                    today=DATE,
                )
            state = st.read_state(run_dir)
            report = spawn_harness.verify_stage(run_dir, "extraction", state)
            self.assertTrue(report["reconciled"])
            self.assertFalse(report["blocking"])
            self.assertEqual(report["satisfied"], 2)

    def test_skipped_with_reason_reconciles(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a", "src-b"])
            _write_extraction_output(run_dir, "src-a")
            _set_stage_direct(run_dir, "extraction")
            orch.cmd_record_spawn(
                run_dir,
                stage="extraction",
                agent_type=spawn_harness.SOURCE_EXTRACTOR,
                unit="src-a",
                today=DATE,
            )
            orch.cmd_record_spawn(
                run_dir,
                stage="extraction",
                agent_type=spawn_harness.SOURCE_EXTRACTOR,
                unit="src-b",
                status="skipped",
                reason="unreadable PDF, quarantined",
                today=DATE,
            )
            state = st.read_state(run_dir)
            report = spawn_harness.verify_stage(run_dir, "extraction", state)
            self.assertTrue(report["reconciled"])
            self.assertEqual(len(report["skipped"]), 1)

    def test_completed_spawn_is_rejected_before_missing_output_can_be_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _set_stage_direct(run_dir, "extraction")
            with self.assertRaisesRegex(orch.OrchestratorError, "required output artifact"):
                orch.cmd_record_spawn(
                    run_dir,
                    stage="extraction",
                    agent_type=spawn_harness.SOURCE_EXTRACTOR,
                    unit="src-a",
                    today=DATE,
                )

    def test_quality_reviewer_is_non_skippable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _set_stage_direct(run_dir, "completeness_review")
            with self.assertRaisesRegex(orch.OrchestratorError, "may not be skipped"):
                orch.cmd_record_spawn(
                    run_dir,
                    stage="completeness_review",
                    agent_type=spawn_harness.QUALITY_REVIEWER,
                    unit="completeness_review",
                    status="skipped",
                    reason="trying to skip",
                    today=DATE,
                )


class RecordSpawnTests(unittest.TestCase):
    def test_skip_requires_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _set_stage_direct(run_dir, "extraction")
            with self.assertRaises(st.StateError):
                orch.cmd_record_spawn(
                    run_dir,
                    stage="extraction",
                    agent_type=spawn_harness.SOURCE_EXTRACTOR,
                    unit="src-a",
                    status="skipped",
                    today=DATE,
                )

    def test_record_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _set_stage_direct(run_dir, "extraction")
            orch.cmd_record_spawn(
                run_dir, stage="extraction", agent_type="x", unit="u", today=DATE
            )
            orch.cmd_record_spawn(
                run_dir, stage="extraction", agent_type="x", unit="u", today=DATE
            )
            state = st.read_state(run_dir)
            self.assertEqual(len(st.spawn_jobs_for_stage(state, "extraction")), 1)

    def test_governed_agent_rejects_arbitrary_manifest_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _set_stage_direct(run_dir, "extraction")
            with self.assertRaisesRegex(orch.OrchestratorError, "not an expected unit"):
                orch.cmd_record_spawn(
                    run_dir,
                    stage="extraction",
                    agent_type=spawn_harness.SOURCE_EXTRACTOR,
                    unit="research-lettuce",
                    today=DATE,
                )

    def test_post_hoc_spawn_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _write_extraction_output(run_dir, "src-a")
            _set_stage_direct(run_dir, "normalization_and_selection")
            with self.assertRaisesRegex(orch.OrchestratorError, "while current stage"):
                orch.cmd_record_spawn(
                    run_dir,
                    stage="extraction",
                    agent_type=spawn_harness.SOURCE_EXTRACTOR,
                    unit="src-a",
                    today=DATE,
                )


class SetStageGateTests(unittest.TestCase):
    def test_evidence_collection_cannot_advance_without_master_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _set_stage_direct(run_dir, "evidence_collection")
            with self.assertRaisesRegex(orch.OrchestratorError, "unaccounted"):
                orch.cmd_set_stage(run_dir, "extraction", today=DATE)

    def test_evidence_collection_advances_after_canonical_screener_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_master_search(run_dir)
            _set_stage_direct(run_dir, "evidence_collection")
            orch.cmd_record_spawn(
                run_dir,
                stage="evidence_collection",
                agent_type=spawn_harness.RESEARCH_SCREENER,
                unit="master-list",
                today=DATE,
            )
            result = orch.cmd_set_stage(run_dir, "extraction", today=DATE)
            self.assertEqual(result["stage"], "extraction")

    def test_declared_gap_fill_must_run_before_leaving_evidence_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_master_search(run_dir, gaps=["growth"])
            _set_stage_direct(run_dir, "evidence_collection")
            orch.cmd_record_spawn(
                run_dir,
                stage="evidence_collection",
                agent_type=spawn_harness.RESEARCH_SCREENER,
                unit="master-list",
                today=DATE,
            )
            with self.assertRaisesRegex(orch.OrchestratorError, "gap-fill:growth"):
                orch.cmd_set_stage(run_dir, "extraction", today=DATE)
            _write_gap_search(run_dir, "growth")
            orch.cmd_record_spawn(
                run_dir,
                stage="evidence_collection",
                agent_type=spawn_harness.RESEARCH_SCREENER,
                unit="gap-fill:growth",
                today=DATE,
            )
            result = orch.cmd_set_stage(run_dir, "extraction", today=DATE)
            self.assertEqual(result["stage"], "extraction")

    def test_forward_move_blocks_without_spawns(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _set_stage_direct(run_dir, "extraction")
            with self.assertRaises(orch.OrchestratorError) as ctx:
                orch.cmd_set_stage(run_dir, "normalization_and_selection", today=DATE)
            self.assertIn("unaccounted", str(ctx.exception))

    def test_forward_move_passes_after_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _write_extraction_output(run_dir, "src-a")
            _set_stage_direct(run_dir, "extraction")
            orch.cmd_record_spawn(
                run_dir,
                stage="extraction",
                agent_type=spawn_harness.SOURCE_EXTRACTOR,
                unit="src-a",
                today=DATE,
            )
            _set_stage_direct(run_dir, "extraction")
            result = orch.cmd_set_stage(run_dir, "normalization_and_selection", today=DATE)
            self.assertEqual(result["stage"], "normalization_and_selection")

    def test_rewind_is_never_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            _set_stage_direct(run_dir, "extraction")
            # rewinding to an earlier stage must not be blocked by the gate
            result = orch.cmd_set_stage(run_dir, "evidence_collection", today=DATE)
            self.assertEqual(result["stage"], "evidence_collection")


if __name__ == "__main__":
    unittest.main()
