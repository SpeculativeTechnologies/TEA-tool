"""Durable run state and issue ledger for the TEA orchestrator.

This module owns two small JSON artifacts that live at a run's root (a single
run folder, or a comparison project folder):

- ``orchestrator-state.json`` — a concise, versioned marker plus the current
  stage/status, execution mode, confirmed intake facts, per-option phase
  status, approval records with artifact hashes, the aggregate issue count and
  next id, active blockers, and the next safe action. It never stores the chat
  transcript.
- ``issues.json`` — the actionable issue ledger (blocking failures and user
  decisions only), with stable ids and a monotonic counter.

The deterministic orchestration CLI (``scripts/orchestrator.py``) is the only
writer; the conversational skill calls the CLI rather than editing JSON. Keeping
the state/issue contract here means the skill never has to maintain fragile JSON
by hand (orchestrator §5/§7/§12 Phase A).

Dates are passed in (``today``) so the helpers stay deterministic under test;
the CLI defaults to the system date.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping

from .schema import EXECUTION_MODES


# ---------------------------------------------------------------------------
# Versioned contract constants
# ---------------------------------------------------------------------------

#: Identifies a folder as a tea-orchestrator run. V1 adopts only its own runs.
ORCHESTRATOR_MARKER = "tea-orchestrator"
ORCHESTRATOR_VERSION = "1"
#: Bumped when the deterministic contracts change in a way that older runs
#: cannot be safely resumed against.
REPO_COMPAT_VERSION = "1"

STATE_FILENAME = "orchestrator-state.json"
ISSUES_FILENAME = "issues.json"

#: Compact workflow stages (orchestrator §5). Ordered; forward moves advance one
#: stage, and any earlier stage may be re-entered for a scope amendment.
STAGES = (
    "intake",
    "understanding_review",
    "starting_documents_review",
    "schema_setup",
    "model_build",
    "model_review",
    "evidence_collection",
    "extraction",
    "normalization_and_selection",
    "completeness_review",
    "estimation",
    "finalization",
    "complete",
)

PROJECT_TYPES = frozenset({"single", "comparison"})
STATUSES = frozenset({"in_progress", "blocked", "awaiting_approval", "complete"})

ISSUE_CATEGORIES = frozenset({"blocking", "decision"})
ISSUE_STATUSES = frozenset({"open", "resolved", "dismissed"})

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


class StateError(ValueError):
    """Raised when run state or the issue ledger is malformed or inconsistent."""


# ---------------------------------------------------------------------------
# Slugs and ids
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Return a kebab-case slug for a project or option name."""

    slug = _SLUG_STRIP_RE.sub("-", str(name or "").strip().lower()).strip("-")
    return slug or "run"


def available_slug(runs_dir: str | Path, desired: str) -> str:
    """Return ``desired`` or the first free ``desired-N`` under ``runs_dir``."""

    runs_dir = Path(runs_dir)
    base = slugify(desired)
    if not (runs_dir / base).exists():
        return base
    n = 2
    while (runs_dir / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def hash_file(path: str | Path) -> str:
    """Return ``sha256:<hex>`` for a file's bytes."""

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# State construction / IO
# ---------------------------------------------------------------------------


def new_state(
    *,
    slug: str,
    display_name: str,
    project_type: str,
    run_path: str,
    today: str,
    execution_mode: str = "auto_with_human_gates",
    options: Iterable[Mapping[str, str]] | None = None,
) -> dict:
    """Build a fresh ``orchestrator-state.json`` document."""

    if project_type not in PROJECT_TYPES:
        raise StateError(f"project_type must be one of {sorted(PROJECT_TYPES)}")
    if execution_mode not in EXECUTION_MODES:
        raise StateError(f"execution_mode must be one of {sorted(EXECUTION_MODES)}")
    option_list = [
        {
            "option_id": str(opt.get("option_id") or "").strip(),
            "display_name": str(opt.get("display_name") or "").strip(),
            "phase": "",
            "status": "in_progress",
        }
        for opt in (options or [])
    ]
    return {
        "orchestrator": {
            "marker": ORCHESTRATOR_MARKER,
            "version": ORCHESTRATOR_VERSION,
            "repo_compat": REPO_COMPAT_VERSION,
        },
        "project": {
            "id": slug,
            "slug": slug,
            "display_name": display_name,
            "type": project_type,
            "run_path": run_path,
            "created": today,
        },
        "execution_mode": execution_mode,
        "mode_locked": False,
        "stage": "intake",
        "status": "in_progress",
        "intake_facts": {},
        "options": option_list,
        "workflow_phase": "",
        "approvals": [],
        "issues": {"unresolved": 0, "next_id": 1},
        "blockers": [],
        "next_action": "Inventory supplied materials and confirm the decision, system, and basis.",
        "subagent_jobs": [],
        "updated": today,
    }


def state_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / STATE_FILENAME


def issues_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / ISSUES_FILENAME


def read_state(run_dir: str | Path) -> dict:
    path = state_path(run_dir)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise StateError(f"no orchestrator state at {path}") from None
    except json.JSONDecodeError as exc:
        raise StateError(f"{path}: invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise StateError(f"{path}: state must be a JSON object")
    return data


def write_state(run_dir: str | Path, state: Mapping[str, object], *, today: str | None = None) -> Path:
    state = dict(state)
    if today is not None:
        state["updated"] = today
    path = state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def has_valid_marker(data: Mapping[str, object]) -> bool:
    marker = data.get("orchestrator") if isinstance(data, Mapping) else None
    return isinstance(marker, Mapping) and marker.get("marker") == ORCHESTRATOR_MARKER


def is_orchestrator_run(run_dir: str | Path) -> bool:
    """Whether ``run_dir`` holds a valid orchestrator marker."""

    path = state_path(run_dir)
    if not path.exists():
        return False
    try:
        data = read_state(run_dir)
    except StateError:
        return False
    return has_valid_marker(data)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_state(data: Mapping[str, object]) -> list[str]:
    """Return a list of structural problems in a state document (empty == ok)."""

    errors: list[str] = []
    if not isinstance(data, Mapping):
        return ["state must be a JSON object"]

    marker = data.get("orchestrator")
    if not isinstance(marker, Mapping) or marker.get("marker") != ORCHESTRATOR_MARKER:
        errors.append("orchestrator.marker is missing or not 'tea-orchestrator'")
    elif marker.get("repo_compat") != REPO_COMPAT_VERSION:
        errors.append(
            f"orchestrator.repo_compat {marker.get('repo_compat')!r} != {REPO_COMPAT_VERSION!r}; "
            "this run was created against an incompatible repository version"
        )

    project = data.get("project")
    if not isinstance(project, Mapping):
        errors.append("project block is missing")
    else:
        for key in ("id", "slug", "type", "run_path", "created"):
            if not str(project.get(key) or "").strip():
                errors.append(f"project.{key} is required")
        if project.get("type") not in PROJECT_TYPES:
            errors.append(f"project.type must be one of {sorted(PROJECT_TYPES)}")

    if data.get("stage") not in STAGES:
        errors.append(f"stage must be one of {list(STAGES)}")
    if data.get("status") not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if data.get("execution_mode") not in EXECUTION_MODES:
        errors.append(f"execution_mode must be one of {sorted(EXECUTION_MODES)}")

    issues = data.get("issues")
    if not isinstance(issues, Mapping) or not _is_int(issues.get("next_id")):
        errors.append("issues.next_id must be an integer")

    if not isinstance(data.get("approvals"), list):
        errors.append("approvals must be a list")
    if not isinstance(data.get("options"), list):
        errors.append("options must be a list")

    return errors


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Stage transitions
# ---------------------------------------------------------------------------


def legal_transition(current: str, target: str) -> bool:
    """Forward by exactly one stage, stay put, or rewind to any earlier stage."""

    if current not in STAGES or target not in STAGES:
        return False
    ci, ti = STAGES.index(current), STAGES.index(target)
    return ti <= ci or ti == ci + 1


def set_stage(state: dict, target: str, *, today: str | None = None) -> dict:
    """Advance/rewind the stage, validating the transition."""

    current = str(state.get("stage") or "")
    if target not in STAGES:
        raise StateError(f"unknown stage {target!r}; choose one of {list(STAGES)}")
    if not legal_transition(current, target):
        raise StateError(
            f"illegal stage transition {current!r} -> {target!r}: forward moves advance one "
            "stage at a time (rewind to an earlier stage is allowed for amendments)"
        )
    state["stage"] = target
    if target == "complete":
        state["status"] = "complete"
    if today is not None:
        state["updated"] = today
    return state


# ---------------------------------------------------------------------------
# Approvals + artifact hashing
# ---------------------------------------------------------------------------


def record_approval(
    state: dict,
    *,
    approval_type: str,
    stage: str,
    run_dir: str | Path,
    artifacts: Iterable[str],
    today: str,
    issue_ids: Iterable[str] = (),
) -> dict:
    """Hash the named run-relative artifacts and append an approval record."""

    run_dir = Path(run_dir)
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for name in artifacts:
        target = run_dir / name
        if not target.exists():
            missing.append(name)
            continue
        hashes[name] = hash_file(target)
    if missing:
        raise StateError(f"cannot approve; missing artifact(s): {missing}")
    record = {
        "type": approval_type,
        "stage": stage,
        "date": today,
        "artifacts": hashes,
        "issue_ids": list(issue_ids),
    }
    state.setdefault("approvals", []).append(record)
    state["updated"] = today
    return record


def verify_approvals(state: Mapping[str, object], run_dir: str | Path) -> list[dict]:
    """Re-hash approved artifacts and report which approvals still hold.

    An approval is invalidated when any approved artifact changed or went
    missing outside the orchestrator (orchestrator §5 approval integrity).
    """

    run_dir = Path(run_dir)
    results: list[dict] = []
    for record in state.get("approvals", []):
        if not isinstance(record, Mapping):
            continue
        changed: list[str] = []
        missing: list[str] = []
        for name, recorded in (record.get("artifacts") or {}).items():
            target = run_dir / name
            if not target.exists():
                missing.append(name)
            elif hash_file(target) != recorded:
                changed.append(name)
        results.append(
            {
                "type": record.get("type"),
                "stage": record.get("stage"),
                "date": record.get("date"),
                "ok": not changed and not missing,
                "changed": changed,
                "missing": missing,
            }
        )
    return results


def latest_approval(state: Mapping[str, object], approval_type: str) -> dict | None:
    """Return the most recent approval of a given type, if any."""

    matches = [
        record for record in state.get("approvals", [])
        if isinstance(record, Mapping) and record.get("type") == approval_type
    ]
    return matches[-1] if matches else None


# ---------------------------------------------------------------------------
# Issue ledger
# ---------------------------------------------------------------------------


def new_issue_ledger() -> dict:
    return {"next_id": 1, "issues": []}


def read_issues(run_dir: str | Path) -> dict:
    path = issues_path(run_dir)
    if not path.exists():
        return new_issue_ledger()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise StateError(f"{path}: invalid JSON: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise StateError(f"{path}: issue ledger must have an 'issues' list")
    data.setdefault("next_id", len(data["issues"]) + 1)
    return data


def write_issues(run_dir: str | Path, ledger: Mapping[str, object]) -> Path:
    path = issues_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return path


def validate_issues(ledger: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    if not isinstance(ledger, Mapping):
        return ["issue ledger must be a JSON object"]
    if not _is_int(ledger.get("next_id")):
        errors.append("issues.next_id must be an integer")
    issues = ledger.get("issues")
    if not isinstance(issues, list):
        return errors + ["issues must be a list"]
    seen: set[str] = set()
    for idx, issue in enumerate(issues):
        where = f"issues[{idx}]"
        if not isinstance(issue, Mapping):
            errors.append(f"{where}: must be an object")
            continue
        iid = str(issue.get("id") or "")
        if not iid:
            errors.append(f"{where}: id is required")
        elif iid in seen:
            errors.append(f"{where}: duplicate id {iid!r}")
        else:
            seen.add(iid)
        if issue.get("category") not in ISSUE_CATEGORIES:
            errors.append(f"{where}: category must be one of {sorted(ISSUE_CATEGORIES)}")
        if issue.get("status") not in ISSUE_STATUSES:
            errors.append(f"{where}: status must be one of {sorted(ISSUE_STATUSES)}")
        if not str(issue.get("question") or "").strip():
            errors.append(f"{where}: question is required")
    return errors


def add_issue(
    ledger: dict,
    *,
    category: str,
    question: str,
    recommendation: str = "",
    affected: Mapping[str, str] | None = None,
) -> dict:
    """Append a new issue and return it; bumps the monotonic counter."""

    if category not in ISSUE_CATEGORIES:
        raise StateError(f"issue category must be one of {sorted(ISSUE_CATEGORIES)}")
    if not str(question or "").strip():
        raise StateError("issue question is required")
    next_id = ledger.get("next_id", len(ledger.get("issues", [])) + 1)
    issue = {
        "id": f"ISS-{int(next_id):03d}",
        "category": category,
        "status": "open",
        "affected": {k: str(v) for k, v in (affected or {}).items() if str(v).strip()},
        "question": question,
        "recommendation": recommendation,
        "resolution": {},
    }
    ledger.setdefault("issues", []).append(issue)
    ledger["next_id"] = int(next_id) + 1
    return issue


def resolve_issue(
    ledger: dict,
    issue_id: str,
    *,
    decision: str,
    today: str,
    by: str = "user",
    status: str = "resolved",
    notes: str = "",
) -> dict:
    """Resolve or dismiss an issue, recording resolution metadata."""

    if status not in {"resolved", "dismissed"}:
        raise StateError("issue resolution status must be 'resolved' or 'dismissed'")
    for issue in ledger.get("issues", []):
        if isinstance(issue, Mapping) and issue.get("id") == issue_id:
            issue["status"] = status
            issue["resolution"] = {
                "decision": decision,
                "by": by,
                "date": today,
                "notes": notes,
            }
            return dict(issue)
    raise StateError(f"no issue with id {issue_id!r}")


def unresolved_count(ledger: Mapping[str, object]) -> int:
    return sum(
        1 for issue in ledger.get("issues", [])
        if isinstance(issue, Mapping) and issue.get("status") == "open"
    )


def sync_issue_counters(state: dict, ledger: Mapping[str, object]) -> dict:
    """Mirror the ledger's unresolved count and next id into the state."""

    state.setdefault("issues", {})
    state["issues"]["unresolved"] = unresolved_count(ledger)
    state["issues"]["next_id"] = int(ledger.get("next_id", 1))
    return state
