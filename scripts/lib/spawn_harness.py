"""Anti-shortcut sub-agent spawn harness (workflow note #4).

Runs sometimes take token-saving shortcuts: spawning fewer extractors than
there are slices, or skipping the quality-reviewer pass entirely. This module
makes that impossible to do silently.

The design is deliberately small and reliable:

* **Expected counts are derived, never declared.** They come from artifacts the
  pipeline already builds for this specific TEA — the extraction manifest, the
  estimation manifest — plus the two fixed quality-review passes. So the target
  is always correct for the run at hand without trusting the agent to count.
* **Actual spawns are recorded** through ``orchestrator.py record-spawn`` into
  ``orchestrator-state.json``'s ``subagent_jobs`` ledger.
* **Stage transitions reconcile the two.** A stage is reconciled only when every
  expected unit was either completed or explicitly skipped-with-reason. A silent
  omission leaves a unit unaccounted for and blocks the move; a documented skip
  passes and lands in the audit trail. The quality-reviewer is non-skippable.

A stage with no derivable manifest (e.g. open-ended research rounds) reports
``computable=False`` and is not hard-gated — the harness enforces exactly the
two shortcut modes the workflow calls out, and records the rest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

# Agent-type labels used in the spawn ledger.
SOURCE_EXTRACTOR = "tea-source-extractor"
QUALITY_REVIEWER = "tea-quality-reviewer"
ESTIMATION_POPULATOR = "estimation-populator"

#: Requirements for these agent types may never be satisfied by a documented
#: skip — they must actually run. The quality-reviewer pass is the one the
#: workflow explicitly forbids skipping.
NON_SKIPPABLE = frozenset({QUALITY_REVIEWER})

#: Run-relative manifest locations the harness reads.
EXTRACTION_MANIFEST = Path("extractions") / "extraction_manifest.json"
ESTIMATION_MANIFEST = Path("estimation_manifest.json")

#: Stages with a fixed, manifest-independent requirement.
FIXED_REQUIREMENTS = {
    "completeness_review": [(QUALITY_REVIEWER, "completeness_review")],
    "finalization": [(QUALITY_REVIEWER, "finalization")],
}


def _load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _extraction_requirements(run_dir: Path) -> dict:
    manifest = _load_manifest(run_dir / EXTRACTION_MANIFEST)
    if manifest is None:
        return {
            "stage": "extraction",
            "computable": False,
            "source": str(EXTRACTION_MANIFEST),
            "requirements": [],
            "note": "no extraction manifest yet; nothing to reconcile",
        }
    requirements = []
    for entry in manifest.get("manifest", []):
        if not isinstance(entry, Mapping):
            continue
        unit = str(entry.get("id") or "").strip()
        if not unit:
            continue
        requirements.append(
            {
                "agent_type": SOURCE_EXTRACTOR,
                "unit": unit,
                "artifact": str(entry.get("output_json") or "") or None,
            }
        )
    return {
        "stage": "extraction",
        "computable": True,
        "source": str(EXTRACTION_MANIFEST),
        "requirements": requirements,
    }


def _estimation_requirements(run_dir: Path) -> dict:
    manifest = _load_manifest(run_dir / ESTIMATION_MANIFEST)
    if manifest is None:
        return {
            "stage": "estimation",
            "computable": False,
            "source": str(ESTIMATION_MANIFEST),
            "requirements": [],
            "note": "no estimation manifest yet; nothing to reconcile",
        }
    requirements = []
    for entity in manifest.get("entities", []):
        if not isinstance(entity, Mapping):
            continue
        if not entity.get("blank_parameters"):
            continue
        unit = str(entity.get("entity") or "").strip()
        if not unit:
            continue
        requirements.append({"agent_type": ESTIMATION_POPULATOR, "unit": unit, "artifact": None})
    return {
        "stage": "estimation",
        "computable": True,
        "source": str(ESTIMATION_MANIFEST),
        "requirements": requirements,
    }


def stage_requirements(run_dir: str | Path, stage: str) -> dict:
    """Return the expected sub-agent jobs for ``stage`` (derived, not declared)."""

    run_dir = Path(run_dir)
    if stage == "extraction":
        return _extraction_requirements(run_dir)
    if stage == "estimation":
        return _estimation_requirements(run_dir)
    if stage in FIXED_REQUIREMENTS:
        return {
            "stage": stage,
            "computable": True,
            "source": "fixed",
            "requirements": [
                {"agent_type": atype, "unit": unit, "artifact": None}
                for atype, unit in FIXED_REQUIREMENTS[stage]
            ],
        }
    return {
        "stage": stage,
        "computable": False,
        "source": None,
        "requirements": [],
        "note": "stage has no derivable spawn requirement; jobs are recorded but not gated",
    }


def _artifact_ok(run_dir: Path, artifact: str | None) -> bool:
    if not artifact:
        return True
    path = Path(artifact)
    if not path.is_absolute():
        path = run_dir / path
    return path.exists() and path.stat().st_size > 0


def verify_stage(run_dir: str | Path, stage: str, state: Mapping[str, object]) -> dict:
    """Reconcile expected vs. recorded sub-agent jobs for ``stage``.

    Returns a report with ``reconciled`` True only when every expected unit was
    completed (or skipped-with-reason, where allowed) and every completed unit's
    backstop artifact exists.
    """

    run_dir = Path(run_dir)
    spec = stage_requirements(run_dir, stage)
    requirements = spec["requirements"]

    jobs = [
        job
        for job in state.get("subagent_jobs", [])
        if isinstance(job, Mapping) and job.get("stage") == stage
    ]
    job_index: dict[tuple[str, str], dict] = {
        (str(job.get("agent_type")), str(job.get("unit"))): job for job in jobs
    }

    missing: list[dict] = []
    skipped: list[dict] = []
    artifact_problems: list[dict] = []
    satisfied = 0

    for req in requirements:
        key = (req["agent_type"], req["unit"])
        job = job_index.get(key)
        if job is None:
            missing.append({**req, "why": "no recorded spawn"})
            continue
        status = str(job.get("status") or "")
        if status == "skipped":
            if req["agent_type"] in NON_SKIPPABLE:
                missing.append({**req, "why": "this agent type may not be skipped"})
                continue
            skipped.append({**req, "reason": job.get("reason", "")})
            satisfied += 1
            continue
        # completed
        if not _artifact_ok(run_dir, req.get("artifact")):
            artifact_problems.append({**req, "why": "recorded completed but output artifact is missing/empty"})
            continue
        satisfied += 1

    reconciled = spec["computable"] and not missing and not artifact_problems

    return {
        "stage": stage,
        "computable": spec["computable"],
        "source": spec.get("source"),
        "note": spec.get("note", ""),
        "required": len(requirements),
        "satisfied": satisfied,
        "recorded": len(jobs),
        "missing": missing,
        "skipped": skipped,
        "artifact_problems": artifact_problems,
        # A non-computable stage is never *blocked*, but it is also not a positive
        # "reconciled" claim; callers gate on (computable and reconciled).
        "reconciled": reconciled if spec["computable"] else True,
        "blocking": spec["computable"] and (bool(missing) or bool(artifact_problems)),
    }
