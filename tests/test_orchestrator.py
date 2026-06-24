"""Tests for the orchestration CLI and run-state/issue ledger (Phase A)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrator as orch  # noqa: E402
from lib import orchestrator_state as st  # noqa: E402

DATE = "2026-06-24"


class InitTests(unittest.TestCase):
    def test_init_creates_valid_marker_and_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            result = orch.cmd_init(name="My Run", runs_dir=runs, today=DATE)
            run_dir = runs / "my-run"
            self.assertEqual(result["status"], "initialized")
            self.assertTrue(st.is_orchestrator_run(run_dir))
            state = st.read_state(run_dir)
            self.assertEqual(st.validate_state(state), [])
            self.assertEqual(state["stage"], "intake")
            self.assertEqual(state["orchestrator"]["marker"], "tea-orchestrator")
            for name in ("issues.json", "user-sources.csv", "user-inputs.csv",
                         "provided-materials.json", "decision-log.md"):
                self.assertTrue((run_dir / name).exists(), name)
            for sub in ("provided-materials", "source-staging", "history"):
                self.assertTrue((run_dir / sub).is_dir(), sub)

    def test_init_is_idempotent_for_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            orch.cmd_init(name="My Run", runs_dir=runs, today=DATE)
            again = orch.cmd_init(name="My Run", runs_dir=runs, today=DATE)
            self.assertEqual(again["status"], "exists")

    def test_init_refuses_unknown_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            foreign = runs / "foreign"
            foreign.mkdir(parents=True)
            (foreign / "random.txt").write_text("not ours", encoding="utf-8")
            with self.assertRaises(orch.OrchestratorError) as ctx:
                orch.cmd_init(name="foreign", runs_dir=runs, today=DATE)
            self.assertIn("refusing to adopt", str(ctx.exception))
            self.assertIn("foreign-2", str(ctx.exception))

    def test_init_suffix_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            foreign = runs / "foreign"
            foreign.mkdir(parents=True)
            (foreign / "random.txt").write_text("not ours", encoding="utf-8")
            result = orch.cmd_init(name="foreign", runs_dir=runs, if_exists="suffix", today=DATE)
            self.assertEqual(result["slug"], "foreign-2")

    def test_comparison_state_tracks_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            orch.cmd_init(
                name="LED vs Incandescent",
                runs_dir=runs,
                project_type="comparison",
                options=["incandescent:Legacy", "led:LED A19"],
                today=DATE,
            )
            state = st.read_state(runs / "led-vs-incandescent")
            self.assertEqual(state["project"]["type"], "comparison")
            self.assertEqual([o["option_id"] for o in state["options"]], ["incandescent", "led"])


class StageTransitionTests(unittest.TestCase):
    def _run(self, tmp):
        runs = Path(tmp) / "runs"
        orch.cmd_init(name="Run", runs_dir=runs, today=DATE)
        return runs / "run"

    def test_legal_and_illegal_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            orch.cmd_set_stage(run_dir, "understanding_review", today=DATE)
            self.assertEqual(st.read_state(run_dir)["stage"], "understanding_review")
            # Forward skip of more than one stage is rejected.
            with self.assertRaises(st.StateError):
                orch.cmd_set_stage(run_dir, "estimation", today=DATE)
            # Rewind for amendment is allowed.
            orch.cmd_set_stage(run_dir, "intake", today=DATE)
            self.assertEqual(st.read_state(run_dir)["stage"], "intake")

    def test_model_stages_advance_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            for stage in (
                "understanding_review",
                "starting_documents_review",
                "schema_setup",
                "model_build",
                "model_review",
                "evidence_collection",
            ):
                orch.cmd_set_stage(run_dir, stage, today=DATE)
                self.assertEqual(st.read_state(run_dir)["stage"], stage)
            # Skipping a model stage is still rejected: schema_setup -> model_review
            # is a forward jump of two.
            orch.cmd_set_stage(run_dir, "schema_setup", today=DATE)  # rewind is allowed
            with self.assertRaises(st.StateError):
                orch.cmd_set_stage(run_dir, "model_review", today=DATE)


class IssueTests(unittest.TestCase):
    def _run(self, tmp):
        runs = Path(tmp) / "runs"
        orch.cmd_init(name="Run", runs_dir=runs, today=DATE)
        return runs / "run"

    def test_issue_counters_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            first = orch.cmd_issue_add(
                run_dir, category="blocking", question="Units missing?", today=DATE
            )
            self.assertEqual(first["issue"]["id"], "ISS-001")
            self.assertEqual(first["unresolved"], 1)
            state = st.read_state(run_dir)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("ISS-001", state["blockers"])

            second = orch.cmd_issue_add(
                run_dir, category="decision", question="Which price?", today=DATE
            )
            self.assertEqual(second["issue"]["id"], "ISS-002")
            self.assertEqual(second["unresolved"], 2)

            orch.cmd_issue_resolve(
                run_dir, issue_id="ISS-001", decision="documented units", today=DATE
            )
            state = st.read_state(run_dir)
            self.assertEqual(state["issues"]["unresolved"], 1)
            self.assertEqual(state["status"], "in_progress")
            self.assertEqual(state["blockers"], [])
            # next_id keeps climbing even after resolution (counter integrity).
            third = orch.cmd_issue_add(run_dir, category="decision", question="More?", today=DATE)
            self.assertEqual(third["issue"]["id"], "ISS-003")


class ApprovalTests(unittest.TestCase):
    def _run(self, tmp):
        runs = Path(tmp) / "runs"
        orch.cmd_init(name="Run", runs_dir=runs, today=DATE)
        return runs / "run"

    def test_starting_documents_approval_does_not_lock_mode_and_invalidates_on_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            (run_dir / "scope.md").write_text("scope v1", encoding="utf-8")
            (run_dir / "data-requirements.md").write_text("dr v1", encoding="utf-8")
            result = orch.cmd_approve(
                run_dir,
                approval_type="starting_documents",
                artifacts=["scope.md", "data-requirements.md"],
                today=DATE,
            )
            # Mode is no longer locked at starting-documents approval; that moves to
            # set-mode at the start of /tea-data.
            self.assertFalse(result["mode_locked"])

            status = orch.cmd_status(run_dir)
            self.assertEqual(status["approvals"]["invalid"], [])
            self.assertEqual(status["approvals"]["valid"], ["starting_documents"])

            # Edit an approved artifact outside the orchestrator.
            (run_dir / "scope.md").write_text("scope v2 edited", encoding="utf-8")
            resume = orch.cmd_validate_resume(run_dir)
            self.assertEqual(len(resume["invalid_approvals"]), 1)
            self.assertIn("scope.md", resume["invalid_approvals"][0]["changed"])
            self.assertEqual(orch.cmd_status(run_dir)["approvals"]["valid"], [])

    def test_model_approved_records_and_invalidates_on_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            (run_dir / "model.py").write_text("print('m')\n", encoding="utf-8")
            (run_dir / "viz-spec.md").write_text("# viz\n", encoding="utf-8")
            result = orch.cmd_approve(
                run_dir,
                approval_type="model_approved",
                artifacts=["model.py", "viz-spec.md"],
                today=DATE,
            )
            self.assertEqual(result["approval"]["type"], "model_approved")
            # A model approval never touches the execution-mode lock.
            self.assertFalse(result["mode_locked"])
            self.assertIn("model_approved", orch.cmd_status(run_dir)["approvals"]["valid"])

            # A light inline edit to model.py invalidates the approval until re-approved.
            (run_dir / "model.py").write_text("print('m2')\n", encoding="utf-8")
            self.assertNotIn("model_approved", orch.cmd_status(run_dir)["approvals"]["valid"])
            resume = orch.cmd_validate_resume(run_dir)
            self.assertTrue(any(a["type"] == "model_approved" for a in resume["invalid_approvals"]))

    def test_set_mode_locks_and_rejects_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            self.assertFalse(st.read_state(run_dir)["mode_locked"])  # unlocked at init

            locked = orch.cmd_set_mode(run_dir, mode="auto", lock=True, today=DATE)
            self.assertEqual(locked["execution_mode"], "auto")
            self.assertTrue(locked["mode_locked"])
            self.assertTrue(orch.cmd_status(run_dir)["mode_locked"])

            # Re-setting the same locked mode is idempotent.
            self.assertEqual(orch.cmd_set_mode(run_dir, mode="auto", lock=True, today=DATE)["execution_mode"], "auto")

            # Changing a locked mode is refused.
            with self.assertRaises(orch.OrchestratorError):
                orch.cmd_set_mode(run_dir, mode="auto_with_human_gates", today=DATE)

    def test_set_mode_rejects_unknown_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            with self.assertRaises(orch.OrchestratorError):
                orch.cmd_set_mode(run_dir, mode="turbo", today=DATE)

    def test_approve_missing_artifact_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            with self.assertRaises(st.StateError):
                orch.cmd_approve(
                    run_dir, approval_type="starting_documents", artifacts=["nope.md"], today=DATE
                )


class ResumeTests(unittest.TestCase):
    def test_validate_resume_rejects_non_orchestrator_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "foreign"
            run_dir.mkdir()
            (run_dir / "x.txt").write_text("x", encoding="utf-8")
            result = orch.cmd_validate_resume(run_dir)
            self.assertFalse(result["resumable"])

    def test_validate_resume_accepts_fresh_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            orch.cmd_init(name="Run", runs_dir=runs, today=DATE)
            result = orch.cmd_validate_resume(runs / "run")
            self.assertTrue(result["resumable"], result["errors"])


class SnapshotAndMaterialTests(unittest.TestCase):
    def _run(self, tmp):
        runs = Path(tmp) / "runs"
        orch.cmd_init(name="Run", runs_dir=runs, today=DATE)
        return runs / "run"

    def test_snapshot_copies_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            (run_dir / "scope.md").write_text("scope", encoding="utf-8")
            result = orch.cmd_snapshot(
                run_dir, label="starting-documents", artifacts=["scope.md"], timestamp="20260624-120000"
            )
            snap = Path(result["snapshot"])
            self.assertTrue((snap / "scope.md").exists())
            self.assertEqual(result["copied"], ["scope.md"])

    def test_register_material_copy_and_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run(tmp)
            local = Path(tmp) / "notes.csv"
            local.write_text("a,b\n1,2\n", encoding="utf-8")
            copied = orch.cmd_register_material(run_dir, path=str(local), copy=True, today=DATE)
            self.assertEqual(copied["material"]["copied_to"], "provided-materials/notes.csv")
            self.assertTrue(copied["material"]["checksum"].startswith("sha256:"))
            self.assertTrue((run_dir / "provided-materials" / "notes.csv").exists())

            ref = orch.cmd_register_material(
                run_dir, path="https://example.test/data", handling="metadata-only", today=DATE
            )
            self.assertTrue(ref["material"]["is_url"])
            self.assertEqual(ref["material"]["handling"], "metadata-only")
            self.assertFalse(ref["material"]["copied"])
            self.assertEqual(ref["count"], 2)


if __name__ == "__main__":
    unittest.main()
