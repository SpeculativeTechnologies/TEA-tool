"""Anti-shortcut sub-agent spawn harness (workflow note #4).

Runs sometimes take token-saving shortcuts: skipping research, spawning fewer
extractors than there are slices, filling cells outside the estimation lane, or
skipping the quality-reviewer pass entirely. This module makes those stage-level
shortcuts impossible to do silently.

The design is deliberately small and reliable:

* **Expected counts are derived, never declared.** They come from canonical
  research outputs, the extraction manifest, the estimation manifest, and the
  two fixed quality-review passes. So the target is always correct for the run
  at hand without trusting the agent to count.
* **Actual spawns are recorded** through ``orchestrator.py record-spawn`` into
  ``orchestrator-state.json``'s ``subagent_jobs`` ledger.
* **Stage transitions reconcile the two.** A stage is reconciled only when every
  expected unit was either completed or explicitly skipped-with-reason. A silent
  omission leaves a unit unaccounted for and blocks the move; a documented skip
  passes and lands in the audit trail. The quality-reviewer is non-skippable.

Missing research, extraction, or estimation artifacts are contract failures and
block forward progress. They are never interpreted as "nothing to reconcile."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

# Agent-type labels used in the spawn ledger.
RESEARCH_SCREENER = "tea-research-screener"
SOURCE_EXTRACTOR = "tea-source-extractor"
QUALITY_REVIEWER = "tea-quality-reviewer"
ESTIMATION_POPULATOR = "estimation-populator"

#: Requirements for these agent types may never be satisfied by a documented
#: skip — they must actually run. The quality-reviewer pass is the one the
#: workflow explicitly forbids skipping.
NON_SKIPPABLE = frozenset({RESEARCH_SCREENER, QUALITY_REVIEWER})

#: Run-relative manifest locations the harness reads.
EXTRACTION_MANIFEST = Path("extractions") / "extraction_manifest.json"
ESTIMATION_MANIFEST = Path("estimation_manifest.json")

#: Stages with a fixed, manifest-independent requirement.
FIXED_REQUIREMENTS = {
    "completeness_review": [
        (QUALITY_REVIEWER, "completeness_review", "reviews/completeness-review.md")
    ],
    "finalization": [
        (QUALITY_REVIEWER, "finalization", "reviews/finalization-review.md")
    ],
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


def _comparison_roots(run_dir: Path, state: Mapping[str, object]) -> list[tuple[str, Path]]:
    """Return ``(option_id, run-relative root)`` pairs for a comparison run."""

    project = state.get("project") if isinstance(state.get("project"), Mapping) else {}
    if project.get("type") != "comparison":
        return []

    frame = _load_manifest(run_dir / "comparison-frame.json")
    roots: list[tuple[str, Path]] = []
    if frame is not None:
        for option in frame.get("options", []):
            if not isinstance(option, Mapping):
                continue
            option_id = str(option.get("option_id") or "").strip()
            option_root = str(option.get("run_dir") or "").strip()
            if option_id and option_root:
                roots.append((option_id, Path(option_root)))
    if roots:
        return roots

    for option in state.get("options", []):
        if not isinstance(option, Mapping):
            continue
        option_id = str(option.get("option_id") or "").strip()
        if option_id:
            roots.append((option_id, Path("options") / option_id))
    return roots


def _predicted_gap_entities(master: Mapping[str, object]) -> list[str]:
    coverage = master.get("coverage_summary")
    if not isinstance(coverage, Mapping):
        return []
    entities: list[str] = []
    for item in coverage.get("parameters_likely_to_need_gap_fill", []):
        if not isinstance(item, Mapping):
            continue
        entity = str(item.get("entity") or "").strip()
        if entity and entity not in entities:
            entities.append(entity)
    return entities


def _research_requirements(run_dir: Path) -> dict:
    state = _load_manifest(run_dir / "orchestrator-state.json") or {}
    comparison_roots = _comparison_roots(run_dir, state)
    roots = comparison_roots or [("", Path("."))]
    requirements: list[dict[str, object]] = []

    for option_id, root in roots:
        master_path = root / "search-history" / "master-list.json"
        master_unit = f"master-list:{option_id}" if option_id else "master-list"
        requirements.append(
            {
                "agent_type": RESEARCH_SCREENER,
                "unit": master_unit,
                "artifact": str(master_path),
            }
        )
        master = _load_manifest(run_dir / master_path)
        if master is None:
            continue
        for entity in _predicted_gap_entities(master):
            gap_path = root / "search-history" / f"gap-fill-{entity}.json"
            gap_unit = (
                f"gap-fill:{option_id}:{entity}" if option_id else f"gap-fill:{entity}"
            )
            requirements.append(
                {
                    "agent_type": RESEARCH_SCREENER,
                    "unit": gap_unit,
                    "artifact": str(gap_path),
                }
            )

    return {
        "stage": "evidence_collection",
        "computable": True,
        "source": "search-history/master-list.json",
        "requirements": requirements,
        "contract_problems": [],
    }


def _extraction_requirements(run_dir: Path) -> dict:
    state = _load_manifest(run_dir / "orchestrator-state.json") or {}
    comparison_roots = _comparison_roots(run_dir, state)
    roots = comparison_roots or [("", Path("."))]
    requirements: list[dict[str, object]] = []
    contract_problems: list[str] = []

    for option_id, root in roots:
        manifest_path = root / EXTRACTION_MANIFEST
        manifest = _load_manifest(run_dir / manifest_path)
        if manifest is None:
            contract_problems.append(
                f"missing or invalid required manifest: {manifest_path}"
            )
            continue
        for entry in manifest.get("manifest", []):
            if not isinstance(entry, Mapping):
                continue
            entry_id = str(entry.get("id") or "").strip()
            if not entry_id:
                continue
            unit = f"{option_id}:{entry_id}" if option_id else entry_id
            raw_output = str(entry.get("output_json") or "").strip()
            output = Path(raw_output) if raw_output else None
            if option_id and output is not None and not output.is_absolute():
                output = root / "extractions" / output.name
            requirements.append(
                {
                    "agent_type": SOURCE_EXTRACTOR,
                    "unit": unit,
                    "artifact": str(output) if output is not None else None,
                }
            )
    return {
        "stage": "extraction",
        "computable": True,
        "source": str(EXTRACTION_MANIFEST) if not comparison_roots else "comparison options",
        "requirements": requirements,
        "contract_problems": contract_problems,
    }


def _estimation_requirements(run_dir: Path) -> dict:
    state = _load_manifest(run_dir / "orchestrator-state.json") or {}
    comparison_roots = _comparison_roots(run_dir, state)
    roots = comparison_roots or [("", Path("."))]
    requirements: list[dict[str, object]] = []
    contract_problems: list[str] = []

    for option_id, root in roots:
        manifest_path = root / ESTIMATION_MANIFEST
        manifest = _load_manifest(run_dir / manifest_path)
        if manifest is None:
            contract_problems.append(
                f"missing or invalid required manifest: {manifest_path}"
            )
            continue
        for entity in manifest.get("entities", []):
            if not isinstance(entity, Mapping) or not entity.get("blank_parameters"):
                continue
            entity_id = str(entity.get("entity") or "").strip()
            if not entity_id:
                continue
            unit = f"{option_id}:{entity_id}" if option_id else entity_id
            requirements.append(
                {"agent_type": ESTIMATION_POPULATOR, "unit": unit, "artifact": None}
            )
    return {
        "stage": "estimation",
        "computable": True,
        "source": str(ESTIMATION_MANIFEST) if not comparison_roots else "comparison options",
        "requirements": requirements,
        "contract_problems": contract_problems,
    }


def stage_requirements(run_dir: str | Path, stage: str) -> dict:
    """Return the expected sub-agent jobs for ``stage`` (derived, not declared)."""

    run_dir = Path(run_dir)
    if stage == "evidence_collection":
        return _research_requirements(run_dir)
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
                {"agent_type": atype, "unit": unit, "artifact": artifact}
                for atype, unit, artifact in FIXED_REQUIREMENTS[stage]
            ],
            "contract_problems": [],
        }
    return {
        "stage": stage,
        "computable": False,
        "source": None,
        "requirements": [],
        "contract_problems": [],
        "note": "stage has no derivable spawn requirement; jobs are recorded but not gated",
    }


def _artifact_ok(run_dir: Path, artifact: str | None) -> bool:
    if not artifact:
        return True
    path = Path(artifact)
    if not path.is_absolute():
        path = run_dir / path
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if path.suffix.lower() == ".json":
        return _load_manifest(path) is not None
    return True


def expected_requirement(
    run_dir: str | Path,
    stage: str,
    agent_type: str,
    unit: str,
) -> dict | None:
    """Return the exact expected requirement for a spawn ledger key."""

    for requirement in stage_requirements(run_dir, stage).get("requirements", []):
        if (
            requirement.get("agent_type") == agent_type
            and requirement.get("unit") == unit
        ):
            return dict(requirement)
    return None


def requirement_artifact_ok(run_dir: str | Path, requirement: Mapping[str, object]) -> bool:
    """Return whether an expected job's required output artifact is ready."""

    return _artifact_ok(Path(run_dir), str(requirement.get("artifact") or "") or None)


def verify_stage(run_dir: str | Path, stage: str, state: Mapping[str, object]) -> dict:
    """Reconcile expected vs. recorded sub-agent jobs for ``stage``.

    Returns a report with ``reconciled`` True only when every expected unit was
    completed (or skipped-with-reason, where allowed) and every completed unit's
    backstop artifact exists.
    """

    run_dir = Path(run_dir)
    spec = stage_requirements(run_dir, stage)
    requirements = spec["requirements"]
    contract_problems = list(spec.get("contract_problems") or [])

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

    reconciled = (
        spec["computable"]
        and not contract_problems
        and not missing
        and not artifact_problems
    )

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
        "contract_problems": contract_problems,
        # A non-computable stage is never *blocked*, but it is also not a positive
        # "reconciled" claim; callers gate on (computable and reconciled).
        "reconciled": reconciled if spec["computable"] else True,
        "blocking": spec["computable"] and (
            bool(contract_problems) or bool(missing) or bool(artifact_problems)
        ),
    }
