"""Deterministic orchestration CLI for the TEA orchestrator skill.

The conversational skill keeps the user-facing experience natural language and
calls these subcommands internally for everything that must be exact: run
initialization, state/issue bookkeeping, approvals with artifact hashes,
semantic snapshots, supplied-material registration, and analyst-input
materialization. Every subcommand prints a concise JSON summary on stdout so the
skill can read the result without parsing prose (orchestrator §7).

    python scripts/orchestrator.py init --name "LED vs Incandescent" --type comparison \
        --option incandescent:"Legacy Incandescent" --option led:"LED A19"
    python scripts/orchestrator.py status --run-dir runs/led-vs-incandescent
    python scripts/orchestrator.py validate-resume --run-dir runs/led-vs-incandescent
    python scripts/orchestrator.py issue add --run-dir RUN --category decision --question "..."
    python scripts/orchestrator.py approve --run-dir RUN --type starting_documents \
        --artifact scope.md --artifact data-requirements.md --artifact model-requirements.md
    python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
        --artifact model.py --artifact viz-spec.md
    python scripts/orchestrator.py set-mode --run-dir RUN --mode auto_with_human_gates --lock
    python scripts/orchestrator.py snapshot --run-dir RUN --label starting-documents \
        --artifact scope.md --artifact data-requirements.md
    python scripts/orchestrator.py register-material --run-dir RUN --path notes.xlsx --copy
    python scripts/orchestrator.py materialize-user-inputs --run-dir RUN

The deterministic TEA phase scripts (build_csvs, normalize, consolidate, ...)
remain authoritative; this CLI does not reimplement them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from lib import orchestrator_state as st
from lib import spawn_harness
from lib.csvio import SOURCES_FIELDNAMES, USER_INPUTS_FIELDNAMES, write_rows
from lib.user_inputs import UserInputError, materialize_user_inputs

PROVIDED_MATERIALS_FILE = "provided-materials.json"
HANDLING_POLICIES = ("local-only", "metadata-only", "normal-processing")
RUN_SUBDIRS = ("provided-materials", "source-staging", "history")


class OrchestratorError(ValueError):
    """Raised for operational CLI failures (refusals, bad arguments)."""


def _today(value: str | None) -> str:
    return value or datetime.now().strftime("%Y-%m-%d")


def _timestamp(value: str | None) -> str:
    return value or datetime.now().strftime("%Y%m%d-%H%M%S")


def _dir_is_empty(path: Path) -> bool:
    return not any(path.iterdir())


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _parse_options(specs: list[str]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for spec in specs or []:
        option_id, _, display = spec.partition(":")
        option_id = option_id.strip()
        if not option_id:
            raise OrchestratorError(f"option spec {spec!r} must be option_id[:display name]")
        options.append({"option_id": option_id, "display_name": (display.strip() or option_id)})
    return options


def cmd_init(
    *,
    name: str,
    runs_dir: str | Path = "runs",
    project_type: str = "single",
    slug: str | None = None,
    mode: str = "auto_with_human_gates",
    options: list[str] | None = None,
    if_exists: str = "error",
    today: str | None = None,
) -> dict:
    """Idempotently initialize a run folder; never adopt an unknown folder."""

    today = _today(today)
    runs_dir = Path(runs_dir)
    desired = slug or st.slugify(name)
    target = runs_dir / desired

    if target.exists() and not target.is_dir():
        raise OrchestratorError(f"{target} exists and is not a directory")

    if target.is_dir() and not _dir_is_empty(target):
        if st.is_orchestrator_run(target):
            # Idempotent: a valid run already lives here. Offer resume, do not clobber.
            state = st.read_state(target)
            return {
                "status": "exists",
                "run_path": str(target).replace("\\", "/"),
                "slug": desired,
                "stage": state.get("stage"),
                "message": "valid orchestrator run already present; use validate-resume",
            }
        # Non-empty folder with no orchestrator marker: never merge.
        suggestion = st.available_slug(runs_dir, desired)
        if if_exists == "suffix":
            desired = suggestion
            target = runs_dir / desired
        else:
            raise OrchestratorError(
                f"{target} is a non-empty folder without a tea-orchestrator marker; "
                f"refusing to adopt it. Re-run with slug {suggestion!r} or --if-exists suffix."
            )

    target.mkdir(parents=True, exist_ok=True)
    option_specs = _parse_options(options or [])
    if project_type == "single" and option_specs:
        raise OrchestratorError("options are only valid for --type comparison")

    state = st.new_state(
        slug=desired,
        display_name=name,
        project_type=project_type,
        run_path=str(target).replace("\\", "/"),
        today=today,
        execution_mode=mode,
        options=option_specs,
    )
    st.write_state(target, state)
    st.write_issues(target, st.new_issue_ledger())

    for sub in RUN_SUBDIRS:
        sub_path = target / sub
        sub_path.mkdir(parents=True, exist_ok=True)
        (sub_path / ".gitkeep").touch(exist_ok=True)

    materials_path = target / PROVIDED_MATERIALS_FILE
    if not materials_path.exists():
        materials_path.write_text(json.dumps({"materials": []}, indent=2) + "\n", encoding="utf-8")

    user_sources = target / "user-sources.csv"
    if not user_sources.exists():
        write_rows(user_sources, SOURCES_FIELDNAMES, [])
    user_inputs = target / "user-inputs.csv"
    if not user_inputs.exists():
        write_rows(user_inputs, USER_INPUTS_FIELDNAMES, [])

    decision_log = target / "decision-log.md"
    if not decision_log.exists():
        decision_log.write_text(
            f"# Decision Log - {name}\n\n"
            "Readable rationale for orchestrator decisions and resolved issues.\n",
            encoding="utf-8",
        )

    return {
        "status": "initialized",
        "run_path": str(target).replace("\\", "/"),
        "slug": desired,
        "project_type": project_type,
        "execution_mode": mode,
        "stage": state["stage"],
        "options": [o["option_id"] for o in option_specs],
    }


# ---------------------------------------------------------------------------
# status / validate-resume
# ---------------------------------------------------------------------------


def _issue_breakdown(ledger: dict) -> dict:
    counts = {"open": 0, "resolved": 0, "dismissed": 0}
    for issue in ledger.get("issues", []):
        status = issue.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def cmd_status(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    ledger = st.read_issues(run_dir)
    approvals = st.verify_approvals(state, run_dir)
    invalid = [a for a in approvals if not a["ok"]]
    return {
        "slug": state.get("project", {}).get("slug"),
        "display_name": state.get("project", {}).get("display_name"),
        "type": state.get("project", {}).get("type"),
        "stage": state.get("stage"),
        "status": state.get("status"),
        "execution_mode": state.get("execution_mode"),
        "mode_locked": state.get("mode_locked", False),
        "issues": {
            "unresolved": st.unresolved_count(ledger),
            "breakdown": _issue_breakdown(ledger),
        },
        "blockers": state.get("blockers", []),
        "next_action": state.get("next_action", ""),
        "approvals": {
            "count": len(approvals),
            "valid": sorted({a["type"] for a in approvals if a["ok"]}),
            "invalid": [{"type": a["type"], "changed": a["changed"], "missing": a["missing"]} for a in invalid],
        },
        "options": [
            {"option_id": o.get("option_id"), "phase": o.get("phase"), "status": o.get("status")}
            for o in state.get("options", [])
        ],
    }


def cmd_validate_resume(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    errors: list[str] = []
    if not st.is_orchestrator_run(run_dir):
        return {
            "resumable": False,
            "errors": [f"{run_dir} has no valid tea-orchestrator marker; V1 resumes only its own runs"],
        }
    state = st.read_state(run_dir)
    errors += st.validate_state(state)
    try:
        ledger = st.read_issues(run_dir)
        errors += st.validate_issues(ledger)
    except st.StateError as exc:
        errors.append(str(exc))
        ledger = st.new_issue_ledger()

    approvals = st.verify_approvals(state, run_dir)
    invalid = [a for a in approvals if not a["ok"]]

    return {
        "resumable": not errors,
        "errors": errors,
        "stage": state.get("stage"),
        "status": state.get("status"),
        "invalid_approvals": [
            {"type": a["type"], "stage": a["stage"], "changed": a["changed"], "missing": a["missing"]}
            for a in invalid
        ],
        "unresolved_issues": st.unresolved_count(ledger),
        "next_action": state.get("next_action", ""),
    }


def _forward_move(current: str, target: str) -> bool:
    """A forward move advances exactly one stage (rewinds are amendments)."""

    if current not in st.STAGES or target not in st.STAGES:
        return False
    return st.STAGES.index(target) == st.STAGES.index(current) + 1


def cmd_set_stage(
    run_dir: str | Path,
    stage: str,
    *,
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    current = str(state.get("stage") or "")

    # Anti-shortcut gate: when advancing forward, the stage being left must have
    # every expected sub-agent job accounted for (run or skipped-with-reason).
    # Rewinds (amendments) are never gated. There is no force override — a
    # legitimate exception is recorded as a skipped job, not waved through.
    if _forward_move(current, stage):
        report = spawn_harness.verify_stage(run_dir, current, state)
        if report["blocking"]:
            raise OrchestratorError(
                f"cannot advance {current!r} -> {stage!r}: the {current!r} stage has "
                f"{len(report['missing'])} unaccounted sub-agent job(s) and "
                f"{len(report['artifact_problems'])} missing output artifact(s). "
                "Run the missing sub-agent(s), or record a documented exception with "
                "`record-spawn --status skipped --reason ...`. "
                f"Details: missing={report['missing']}, "
                f"artifact_problems={report['artifact_problems']}"
            )

    st.set_stage(state, stage, today=_today(today))
    st.write_state(run_dir, state, today=_today(today))
    return {"stage": state["stage"], "status": state["status"]}


def cmd_record_spawn(
    run_dir: str | Path,
    *,
    stage: str,
    agent_type: str,
    unit: str,
    status: str = "completed",
    reason: str = "",
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    entry = st.record_spawn(
        state,
        stage=stage,
        agent_type=agent_type,
        unit=unit,
        status=status,
        reason=reason,
        today=_today(today),
    )
    st.write_state(run_dir, state, today=_today(today))
    return {"recorded": entry, "stage_total": len(st.spawn_jobs_for_stage(state, stage))}


def cmd_expected_spawns(run_dir: str | Path, stage: str) -> dict:
    return spawn_harness.stage_requirements(run_dir, stage)


def cmd_verify_spawns(run_dir: str | Path, stage: str) -> dict:
    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    return spawn_harness.verify_stage(run_dir, stage, state)


# ---------------------------------------------------------------------------
# issues
# ---------------------------------------------------------------------------


def _parse_affected(specs: list[str]) -> dict[str, str]:
    affected: dict[str, str] = {}
    for spec in specs or []:
        key, _, value = spec.partition("=")
        if key.strip():
            affected[key.strip()] = value.strip()
    return affected


def cmd_issue_add(
    run_dir: str | Path,
    *,
    category: str,
    question: str,
    recommendation: str = "",
    affected: list[str] | None = None,
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    ledger = st.read_issues(run_dir)
    issue = st.add_issue(
        ledger,
        category=category,
        question=question,
        recommendation=recommendation,
        affected=_parse_affected(affected or []),
    )
    st.write_issues(run_dir, ledger)
    state = st.read_state(run_dir)
    st.sync_issue_counters(state, ledger)
    if category == "blocking" and issue["id"] not in state.get("blockers", []):
        state.setdefault("blockers", []).append(issue["id"])
        if state.get("status") == "in_progress":
            state["status"] = "blocked"
    st.write_state(run_dir, state, today=_today(today))
    return {"issue": issue, "unresolved": state["issues"]["unresolved"]}


def cmd_issue_resolve(
    run_dir: str | Path,
    *,
    issue_id: str,
    decision: str,
    by: str = "user",
    status: str = "resolved",
    notes: str = "",
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    ledger = st.read_issues(run_dir)
    issue = st.resolve_issue(
        ledger, issue_id, decision=decision, by=by, status=status, notes=notes, today=_today(today)
    )
    st.write_issues(run_dir, ledger)
    state = st.read_state(run_dir)
    st.sync_issue_counters(state, ledger)
    state["blockers"] = [b for b in state.get("blockers", []) if b != issue_id]
    if not state["blockers"] and state.get("status") == "blocked":
        state["status"] = "in_progress"
    st.write_state(run_dir, state, today=_today(today))
    return {"issue": issue, "unresolved": state["issues"]["unresolved"]}


def cmd_issue_list(run_dir: str | Path, *, status: str | None = None) -> dict:
    ledger = st.read_issues(run_dir)
    issues = ledger.get("issues", [])
    if status:
        issues = [i for i in issues if i.get("status") == status]
    return {"issues": issues, "unresolved": st.unresolved_count(ledger)}


# ---------------------------------------------------------------------------
# approve / snapshot
# ---------------------------------------------------------------------------


def cmd_approve(
    run_dir: str | Path,
    *,
    approval_type: str,
    artifacts: list[str],
    stage: str | None = None,
    issue_ids: list[str] | None = None,
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    record = st.record_approval(
        state,
        approval_type=approval_type,
        stage=stage or state.get("stage", ""),
        run_dir=run_dir,
        artifacts=artifacts,
        today=_today(today),
        issue_ids=issue_ids or [],
    )
    st.write_state(run_dir, state, today=_today(today))
    return {"approval": record, "mode_locked": state.get("mode_locked", False)}


def cmd_set_mode(
    run_dir: str | Path,
    *,
    mode: str,
    lock: bool = False,
    today: str | None = None,
) -> dict:
    """Set (and optionally lock) the execution mode.

    The execution mode is chosen at the start of the data-acquisition skill
    (`/tea-data`) and locked once acquisition begins; it governs only the
    downstream gate behavior. A locked mode is immutable: changing it requires a
    new run. Setting the same mode again (idempotent) or merely locking the
    current mode is always allowed.
    """

    run_dir = Path(run_dir)
    state = st.read_state(run_dir)
    if mode not in st.EXECUTION_MODES:
        raise OrchestratorError(f"mode must be one of {sorted(st.EXECUTION_MODES)}")
    current = state.get("execution_mode")
    if state.get("mode_locked") and mode != current:
        raise OrchestratorError(
            f"execution mode is locked at {current!r}; changing it requires a new run"
        )
    state["execution_mode"] = mode
    if lock:
        state["mode_locked"] = True
    st.write_state(run_dir, state, today=_today(today))
    return {"execution_mode": state["execution_mode"], "mode_locked": state.get("mode_locked", False)}


def cmd_snapshot(
    run_dir: str | Path,
    *,
    label: str,
    artifacts: list[str] | None = None,
    timestamp: str | None = None,
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    if not st.is_orchestrator_run(run_dir):
        raise OrchestratorError(f"{run_dir} is not an orchestrator run")
    stamp = _timestamp(timestamp)
    dest = run_dir / "history" / f"{stamp}-{label}"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    missing: list[str] = []
    for name in artifacts or []:
        src = run_dir / name
        if not src.exists():
            missing.append(name)
            continue
        target = dest / Path(name).name
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(src, target)
        copied.append(name)
    if missing:
        raise OrchestratorError(f"cannot snapshot missing artifact(s): {missing}")
    return {
        "snapshot": str(dest).replace("\\", "/"),
        "label": label,
        "copied": copied,
    }


# ---------------------------------------------------------------------------
# register-material
# ---------------------------------------------------------------------------


def _read_materials(run_dir: Path) -> dict:
    path = run_dir / PROVIDED_MATERIALS_FILE
    if not path.exists():
        return {"materials": []}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("materials", [])
    return data


def cmd_register_material(
    run_dir: str | Path,
    *,
    path: str,
    handling: str = "normal-processing",
    copy: bool = False,
    name: str | None = None,
    today: str | None = None,
) -> dict:
    run_dir = Path(run_dir)
    if not st.is_orchestrator_run(run_dir):
        raise OrchestratorError(f"{run_dir} is not an orchestrator run")
    if handling not in HANDLING_POLICIES:
        raise OrchestratorError(f"handling must be one of {list(HANDLING_POLICIES)}")

    is_url = "://" in path
    source = Path(path)
    display_name = name or (path if is_url else source.name)
    checksum = ""
    copied_to = ""
    local_exists = (not is_url) and source.exists() and source.is_file()

    if copy and is_url:
        raise OrchestratorError("cannot copy a URL; register URLs as reference-only")
    if copy and not local_exists:
        raise OrchestratorError(f"cannot copy missing local file: {path}")

    if local_exists:
        checksum = st.hash_file(source)
    if copy and local_exists:
        dest_dir = run_dir / "provided-materials"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        shutil.copyfile(source, dest)
        copied_to = str(dest.relative_to(run_dir)).replace("\\", "/")

    materials = _read_materials(run_dir)
    material_id = f"mat-{len(materials['materials']) + 1:03d}"
    entry = {
        "id": material_id,
        "name": display_name,
        "original": path,
        "is_url": is_url,
        "handling": handling,
        "copied": bool(copied_to),
        "copied_to": copied_to,
        "checksum": checksum,
        "registered": _today(today),
    }
    materials["materials"].append(entry)
    (run_dir / PROVIDED_MATERIALS_FILE).write_text(
        json.dumps(materials, indent=2) + "\n", encoding="utf-8"
    )
    return {"material": entry, "count": len(materials["materials"])}


# ---------------------------------------------------------------------------
# materialize-user-inputs
# ---------------------------------------------------------------------------


def cmd_materialize_user_inputs(
    run_dir: str | Path,
    *,
    schema_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    run_dir = Path(run_dir)
    schema_path = Path(schema_path) if schema_path else run_dir / "tea-schema.json"
    result = materialize_user_inputs(schema_path=schema_path, run_dir=run_dir, dry_run=dry_run)
    return {
        "inputs": result["inputs"],
        "fixed": result["fixed"],
        "sources": result["sources"],
        "audit_rows": result["audit_rows"],
        "dry_run": result["dry_run"],
    }


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _emit(summary: dict) -> None:
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize an idempotent run folder")
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--runs-dir", default="runs")
    p_init.add_argument("--type", dest="project_type", choices=sorted(st.PROJECT_TYPES), default="single")
    p_init.add_argument("--slug")
    p_init.add_argument("--mode", choices=["auto_with_human_gates", "auto"], default="auto_with_human_gates")
    p_init.add_argument("--option", action="append", default=[], help="option_id:Display name (comparison)")
    p_init.add_argument("--if-exists", choices=["error", "suffix"], default="error")
    p_init.add_argument("--date")

    p_status = sub.add_parser("status", help="Concise machine-readable run status")
    p_status.add_argument("--run-dir", required=True)

    p_resume = sub.add_parser("validate-resume", help="Validate a run before resuming")
    p_resume.add_argument("--run-dir", required=True)

    p_stage = sub.add_parser("set-stage", help="Advance or rewind the workflow stage")
    p_stage.add_argument("--run-dir", required=True)
    p_stage.add_argument("--stage", required=True, choices=list(st.STAGES))
    p_stage.add_argument("--date")

    p_spawn = sub.add_parser("record-spawn", help="Record a sub-agent job (anti-shortcut harness)")
    p_spawn.add_argument("--run-dir", required=True)
    p_spawn.add_argument("--stage", required=True, choices=list(st.STAGES))
    p_spawn.add_argument("--agent-type", required=True)
    p_spawn.add_argument("--unit", required=True, help="The unit of work (slice id, entity, gate name)")
    p_spawn.add_argument(
        "--status", choices=sorted(st.SUBAGENT_STATUSES), default="completed"
    )
    p_spawn.add_argument("--reason", default="", help="Required when --status skipped")
    p_spawn.add_argument("--date")

    p_expected = sub.add_parser("expected-spawns", help="Show expected sub-agent jobs for a stage")
    p_expected.add_argument("--run-dir", required=True)
    p_expected.add_argument("--stage", required=True, choices=list(st.STAGES))

    p_verify = sub.add_parser("verify-spawns", help="Reconcile expected vs recorded jobs for a stage")
    p_verify.add_argument("--run-dir", required=True)
    p_verify.add_argument("--stage", required=True, choices=list(st.STAGES))

    p_mode = sub.add_parser("set-mode", help="Set (and optionally lock) the execution mode")
    p_mode.add_argument("--run-dir", required=True)
    p_mode.add_argument("--mode", required=True, choices=sorted(st.EXECUTION_MODES))
    p_mode.add_argument("--lock", action="store_true")
    p_mode.add_argument("--date")

    p_issue = sub.add_parser("issue", help="Add, resolve, or list issues")
    issue_sub = p_issue.add_subparsers(dest="issue_command", required=True)
    p_issue_add = issue_sub.add_parser("add")
    p_issue_add.add_argument("--run-dir", required=True)
    p_issue_add.add_argument("--category", required=True, choices=sorted(st.ISSUE_CATEGORIES))
    p_issue_add.add_argument("--question", required=True)
    p_issue_add.add_argument("--recommendation", default="")
    p_issue_add.add_argument("--affected", action="append", default=[], help="key=value")
    p_issue_add.add_argument("--date")
    p_issue_resolve = issue_sub.add_parser("resolve")
    p_issue_resolve.add_argument("--run-dir", required=True)
    p_issue_resolve.add_argument("--id", dest="issue_id", required=True)
    p_issue_resolve.add_argument("--decision", required=True)
    p_issue_resolve.add_argument("--by", default="user")
    p_issue_resolve.add_argument("--status", choices=["resolved", "dismissed"], default="resolved")
    p_issue_resolve.add_argument("--notes", default="")
    p_issue_resolve.add_argument("--date")
    p_issue_list = issue_sub.add_parser("list")
    p_issue_list.add_argument("--run-dir", required=True)
    p_issue_list.add_argument("--status", choices=sorted(st.ISSUE_STATUSES))

    p_approve = sub.add_parser("approve", help="Record an approval with artifact hashes")
    p_approve.add_argument("--run-dir", required=True)
    p_approve.add_argument("--type", dest="approval_type", required=True)
    p_approve.add_argument("--stage")
    p_approve.add_argument("--artifact", action="append", default=[], required=True)
    p_approve.add_argument("--issue", action="append", default=[])
    p_approve.add_argument("--date")

    p_snapshot = sub.add_parser("snapshot", help="Snapshot artifacts into history/")
    p_snapshot.add_argument("--run-dir", required=True)
    p_snapshot.add_argument("--label", required=True)
    p_snapshot.add_argument("--artifact", action="append", default=[])
    p_snapshot.add_argument("--timestamp")

    p_material = sub.add_parser("register-material", help="Register a supplied material")
    p_material.add_argument("--run-dir", required=True)
    p_material.add_argument("--path", required=True)
    p_material.add_argument("--handling", choices=list(HANDLING_POLICIES), default="normal-processing")
    p_material.add_argument("--copy", action="store_true")
    p_material.add_argument("--name")
    p_material.add_argument("--date")

    p_mat = sub.add_parser("materialize-user-inputs", help="Materialize analyst inputs into Audit/Sources")
    p_mat.add_argument("--run-dir", required=True)
    p_mat.add_argument("--schema")
    p_mat.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            summary = cmd_init(
                name=args.name,
                runs_dir=args.runs_dir,
                project_type=args.project_type,
                slug=args.slug,
                mode=args.mode,
                options=args.option,
                if_exists=args.if_exists,
                today=args.date,
            )
            _emit(summary)
            return 0
        if args.command == "status":
            _emit(cmd_status(args.run_dir))
            return 0
        if args.command == "validate-resume":
            summary = cmd_validate_resume(args.run_dir)
            _emit(summary)
            return 0 if summary["resumable"] else 1
        if args.command == "set-stage":
            _emit(cmd_set_stage(args.run_dir, args.stage, today=args.date))
            return 0
        if args.command == "record-spawn":
            _emit(
                cmd_record_spawn(
                    args.run_dir,
                    stage=args.stage,
                    agent_type=args.agent_type,
                    unit=args.unit,
                    status=args.status,
                    reason=args.reason,
                    today=args.date,
                )
            )
            return 0
        if args.command == "expected-spawns":
            _emit(cmd_expected_spawns(args.run_dir, args.stage))
            return 0
        if args.command == "verify-spawns":
            summary = cmd_verify_spawns(args.run_dir, args.stage)
            _emit(summary)
            return 0 if summary["reconciled"] else 1
        if args.command == "set-mode":
            _emit(cmd_set_mode(args.run_dir, mode=args.mode, lock=args.lock, today=args.date))
            return 0
        if args.command == "issue":
            if args.issue_command == "add":
                _emit(
                    cmd_issue_add(
                        args.run_dir,
                        category=args.category,
                        question=args.question,
                        recommendation=args.recommendation,
                        affected=args.affected,
                        today=args.date,
                    )
                )
            elif args.issue_command == "resolve":
                _emit(
                    cmd_issue_resolve(
                        args.run_dir,
                        issue_id=args.issue_id,
                        decision=args.decision,
                        by=args.by,
                        status=args.status,
                        notes=args.notes,
                        today=args.date,
                    )
                )
            else:
                _emit(cmd_issue_list(args.run_dir, status=args.status))
            return 0
        if args.command == "approve":
            _emit(
                cmd_approve(
                    args.run_dir,
                    approval_type=args.approval_type,
                    artifacts=args.artifact,
                    stage=args.stage,
                    issue_ids=args.issue,
                    today=args.date,
                )
            )
            return 0
        if args.command == "snapshot":
            _emit(
                cmd_snapshot(
                    args.run_dir,
                    label=args.label,
                    artifacts=args.artifact,
                    timestamp=args.timestamp,
                )
            )
            return 0
        if args.command == "register-material":
            _emit(
                cmd_register_material(
                    args.run_dir,
                    path=args.path,
                    handling=args.handling,
                    copy=args.copy,
                    name=args.name,
                    today=args.date,
                )
            )
            return 0
        if args.command == "materialize-user-inputs":
            _emit(
                cmd_materialize_user_inputs(
                    args.run_dir, schema_path=args.schema, dry_run=args.dry_run
                )
            )
            return 0
    except (OrchestratorError, st.StateError, UserInputError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    parser.error(f"unhandled command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
