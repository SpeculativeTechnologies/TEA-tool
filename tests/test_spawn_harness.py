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

    def test_missing_manifest_is_not_computable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            spec = spawn_harness.stage_requirements(run_dir, "extraction")
            self.assertFalse(spec["computable"])

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

    def test_artifact_backstop_flags_missing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            _write_extraction_manifest(run_dir, ["src-a"])
            # recorded completed but no output artifact written
            orch.cmd_record_spawn(
                run_dir,
                stage="extraction",
                agent_type=spawn_harness.SOURCE_EXTRACTOR,
                unit="src-a",
                today=DATE,
            )
            state = st.read_state(run_dir)
            report = spawn_harness.verify_stage(run_dir, "extraction", state)
            self.assertFalse(report["reconciled"])
            self.assertEqual(len(report["artifact_problems"]), 1)

    def test_quality_reviewer_is_non_skippable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
            orch.cmd_record_spawn(
                run_dir,
                stage="completeness_review",
                agent_type=spawn_harness.QUALITY_REVIEWER,
                unit="completeness_review",
                status="skipped",
                reason="trying to skip",
                today=DATE,
            )
            state = st.read_state(run_dir)
            report = spawn_harness.verify_stage(run_dir, "completeness_review", state)
            self.assertFalse(report["reconciled"])
            self.assertEqual(len(report["missing"]), 1)


class RecordSpawnTests(unittest.TestCase):
    def test_skip_requires_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _init_run(tmp)
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
            orch.cmd_record_spawn(
                run_dir, stage="extraction", agent_type="x", unit="u", today=DATE
            )
            orch.cmd_record_spawn(
                run_dir, stage="extraction", agent_type="x", unit="u", today=DATE
            )
            state = st.read_state(run_dir)
            self.assertEqual(len(st.spawn_jobs_for_stage(state, "extraction")), 1)


class SetStageGateTests(unittest.TestCase):
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
