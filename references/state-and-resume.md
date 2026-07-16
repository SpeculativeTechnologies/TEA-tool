# State, issues, approvals, and resume

The orchestrator CLI (`python scripts/orchestrator.py`) owns these artifacts.
Read its JSON output; never hand-edit the JSON/CSV files.

## Run artifacts

```
runs/<project>/
  orchestrator-state.json   # versioned marker, stage/status, mode, intake facts,
                            # per-option phase, approvals + hashes, issue counters,
                            # blockers, next action. No chat transcript.
  issues.json               # actionable blockers + decisions only
  decision-log.md           # readable rationale
  intake-summary.md         # the approved understanding check
  scope-summary.md          # concise human-readable review companion (/tea-scope)
  model-requirements.md     # desired outputs -> required inputs (project-level)
  model.py                  # bespoke runnable model (approved + hashed; /tea-model)
  model/dummy-inputs.csv    # quick dummy values for the dry run (/tea-model)
  viz-spec.md               # chosen visualizations (approved + hashed; /tea-model)
  plots-dummy/              # dummy figures from the dry run (/tea-model); kept, not overwritten
  plots/                    # real rendered figures (/tea-insights)
  model-results-DUMMY.json  # dummy-run outputs (/tea-model)
  model-results.json        # real-run headline outputs (/tea-insights)
  user-inputs.csv           # analyst values mapped to schema cells
  user-sources.csv          # analyst/source registry (source_role may be analyst)
  provided-materials.json   # registered supplied materials
  provided-materials/        source-staging/        history/
```

Comparison projects keep one project-level state and issue ledger at the project
root; option folders hold normal TEA artifacts (`tea-schema.json`, working CSVs,
source buckets) and compact phase status only.

## Stages

`set-stage` advances one stage at a time, or rewinds to any earlier stage for an
amendment (forward skips are rejected):

```
intake → understanding_review → starting_documents_review → schema_setup →
model_build → model_review → evidence_collection → extraction →
normalization_and_selection → completeness_review → estimation → finalization → complete
```

The four skills own contiguous slices: `/tea-scope` runs `intake` …
`starting_documents_review`; `/tea-model` runs `schema_setup` … `model_review`;
`/tea-data` runs `evidence_collection` … `finalization` (stopping at the finalized
inputs); `/tea-insights` runs the approved model on those inputs and advances
`finalization` → `complete`. Each skill refuses to start until the prior skill's
gate approval is recorded and valid (see below).

## Issue ledger

`issues.json` tracks only actionable **blocking** failures and user **decisions**
— not a parallel warning system (existing quality and final-review artifacts own
limitations). Each issue has a stable id (`ISS-001`…), category
(`blocking`|`decision`), status (`open`|`resolved`|`dismissed`), affected
artifact/option/entity/parameter/source, a plain-language question, a recommended
resolution, and resolution metadata. The counter is monotonic — resolved entries
are retained for counter integrity. Put readable rationale in `decision-log.md`.

```
python scripts/orchestrator.py issue add --run-dir RUN --category decision \
    --question "Use EIA 2025 residential price?" --recommendation "Yes" \
    --affected entity=REF --affected parameter=electricity_price
python scripts/orchestrator.py issue resolve --run-dir RUN --id ISS-001 \
    --decision "approved EIA 2025" --by user
python scripts/orchestrator.py issue list --run-dir RUN [--status open]
```

`add`/`resolve` keep `orchestrator-state.json`'s `issues.unresolved`/`next_id` in
sync; a `blocking` issue sets status `blocked` and is cleared on resolution.

## Approval integrity

For each meaningful approval, record approval type, stage, date, artifact hashes,
and relevant issue ids:

```
python scripts/orchestrator.py approve --run-dir RUN --type starting_documents \
    --artifact scope-summary.md --artifact scope.md --artifact process-flow.md \
    --artifact data-requirements.md --artifact model-requirements.md
python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
    --artifact model.py --artifact viz-spec.md
```

The gate approvals are `starting_documents` (end of `/tea-scope`), `model_approved`
(end of `/tea-model`), and `inputs_finalized` (end of `/tea-data`, recorded over
`final/Main Input.csv` + `final/run-manifest.md`). `/tea-insights` gate-checks both
`model_approved` and `inputs_finalized`. A skill gate-checks the prior approval(s)
via `status` → `approvals.valid` and refuses to proceed if any is absent. If an
approved file changes outside the orchestrator, `status`/`validate-resume` report
the approval as invalid (changed/missing artifacts) and it drops out of
`approvals.valid`. A light inline `model.py` fix in `/tea-insights` therefore
invalidates `model_approved` until you re-`approve` it (refreshing the hash) —
this is how the model never silently drifts from its approved state.

Execution mode is **not** locked at any approval. It is set and locked once via
`set-mode --lock` at the start of `/tea-data` (it only governs the
data-acquisition gates); thereafter changing it requires a new run.

Snapshot only meaningful semantic boundaries (not routine CSV churn):

```
python scripts/orchestrator.py snapshot --run-dir RUN --label starting-documents \
    --artifact scope-summary.md --artifact scope.md --artifact process-flow.md \
    --artifact data-requirements.md --artifact model-requirements.md
```

→ `history/<timestamp>-starting-documents/`. Other labels: `model-approved`,
`inputs-finalized`, `scope-amendment`.

## Resume behavior

```
python scripts/orchestrator.py validate-resume --run-dir RUN
```

Validates the marker + repo-compat version, state and issue schemas, approval
hashes, and reports `resumable`, the current stage, invalid approvals, unresolved
issues, and the next safe action. On startup:

- If one obvious unfinished orchestrator run exists, summarize it and ask to
  resume.
- If several exist, list concise choices.
- Never silently continue from a previous session.
- Never adopt a folder without a valid `tea-orchestrator` marker (V1 does not
  adopt pre-existing TEA runs).

## Status

```
python scripts/orchestrator.py status --run-dir RUN
```

Returns a concise machine summary: slug, type, stage, status, mode, mode_locked,
unresolved issue count + breakdown, blockers, next action, the valid + invalid
approval types (skills gate on `approvals.valid`), and per-option phase. Use it to
build the Guided decision card's "N issues remaining" and to decide the next safe
action.

## CLI quick reference

| Subcommand | Purpose |
|---|---|
| `init` | Idempotently create a run; refuse unknown folders |
| `status` | Concise machine-readable run status |
| `validate-resume` | Validate a run before resuming |
| `set-stage` | Advance or rewind the workflow stage |
| `set-mode` | Set + optionally lock the execution mode (at `/tea-data` start) |
| `issue add/resolve/list` | Maintain the issue ledger + counters |
| `approve` | Record an approval with artifact hashes (`starting_documents`, `model_approved`, `inputs_finalized`) |
| `snapshot` | Snapshot artifacts into `history/` |
| `register-material` | Register a supplied material (copy or reference) |
| `materialize-user-inputs` | Validate + materialize analyst inputs into Audit/Sources |

Every subcommand prints a JSON summary on stdout and exits non-zero on
operational failure (with `{"error": ...}` on stderr).
