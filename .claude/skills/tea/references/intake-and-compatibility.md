# Intake and compatibility

Detailed contract for the mandatory intake and approval flow. The skill body
gives the sequence; this is the substance. Keep schemas, files, and CSVs
invisible to the user — derive what you can, ask only consequential gaps.

## Step 1 — Initialize early

After you know the project name and whether it is a single run or a comparison:

```
python scripts/orchestrator.py init --name "<name>" [--type single|comparison] \
    [--option <id>:"<display>" ...] [--mode auto_with_human_gates|auto]
```

`init` creates `runs/<slug>/` with `orchestrator-state.json`, `issues.json`,
`decision-log.md`, `user-sources.csv`, `user-inputs.csv`,
`provided-materials.json`, and the `provided-materials/`, `source-staging/`, and
`history/` folders. It is idempotent (a second `init` on a valid run returns
`status: exists`) and **refuses to adopt a non-orchestrator folder** — if the
slug is taken by an unknown folder it errors with a suggested free slug; re-run
with that slug or `--if-exists suffix`. Begin persisting confirmed facts in
state and rationale in `decision-log.md`.

## Step 1b — Inventory supplied materials

Accept any mix of plain-language answers, local documents/PDFs/spreadsheets,
existing models/formulas, URLs, and user-supplied values. Register each:

```
python scripts/orchestrator.py register-material --run-dir RUN --path <file-or-url> \
    [--copy] [--handling local-only|metadata-only|normal-processing] [--name "..."]
```

Copy trusted local inputs into `provided-materials/` (`--copy`) preserving
filenames; permit reference-only registration for very large or sensitive files.
`register-material` records original path/URL, checksum, handling policy, and
copy-vs-reference status.

Inspect supplied material **before** asking questions. For large or independent
files, fan out read-only materials-analyst subagents (one per file/model) and
collect concise structured summaries. Inspect formulas, assumptions, units, and
outputs of any supplied model, but do not modify or execute it unless the user
separately asks.

## Step 2 — Choose execution mode

Ask early, in novice language:

- **Guided** (`auto_with_human_gates`, default): pauses for consequential
  judgments.
- **Hands-off** (`auto`): resolves downstream gates automatically and documents
  assumptions.

Revisable during intake; immutable once the starting documents are approved
(changing it later requires a new run). `approve --type starting_documents` sets
`mode_locked`.

## Step 3 — Inspect and classify supplied values

Ask once: *"Are any supplied numbers requirements or assumptions that research
must not replace?"* Classify each mapped value:

- **Fixed input** (`fixed=TRUE`): authoritative unless the user explicitly
  changes it. Suppresses replacement research for that cell.
- **Candidate evidence** (`fixed` blank): retained, but normal research still
  proceeds and may out-rank it.

Only values that map to a proposed schema cell go in `user-inputs.csv`
(`input_origin`: `analyst` for a direct assertion/model assumption, `extracted`
when the user is fixing a value an uploaded third-party doc reported — origin
preserved, `shared` for a fixed shared assumption). A coherent conversational
batch may share one synthetic `analyst` source in `user-sources.csv`. If a value
cannot be mapped, explain why and offer a valid schema change; discard it as a
pipeline input if the user declines or confirms it is irrelevant. Fixed status
is per target cell, never per whole document.

## Step 4 — Compatibility review

Check, and surface mismatches plainly:

- Desired outputs can be supported by the proposed inputs.
- Comparison options provide an equivalent function (equivalence, not identical
  schemas).
- The functional unit is measurable.
- Boundaries and geography/time/currency bases are coherent.
- Proposed parameters support the desired outputs.
- Supplied values have interpretable units and bases.
- Materially different scenarios are not collapsed into one run.

Blocking failures pause intake (raise a `blocking` issue). Nonblocking
uncertainties become assumptions in the understanding check. Methodological
overrides are allowed and recorded when technically valid; mechanically invalid
configurations are not. When input is incompatible, explain the mismatch,
propose the smallest viable correction, and allow a documented override if valid.

Limited research during intake may inform proposed framing — distinguish
user-confirmed system definitions from public facts and unresolved placeholders.
Any numeric evidence found during intake must later enter the normal evidence
pipeline. For three or more comparison options, warn once that research volume,
review burden, and comparability risk increase, then require confirmation.

Use the standard A–E quality definitions unless the user requests a custom
scheme. Infer estimation policies from calculation structure and parameter
types; ask only when the choice would materially change the result. Validation
targets are optional.

## Step 5 — Understanding check

Before writing any formal document, summarize: the decision; the system or
options; the boundary; the functional unit; basis assumptions; desired outputs;
supplied evidence and fixed inputs; proposed entities and input categories;
major assumptions and unresolved questions. Require correction or approval.
Record the summary in `intake-summary.md`.

## Step 6 — Generate the starting documents

You write `scope.md`, `data-requirements.md`, and `model-requirements.md` (never
the user). `model-requirements.md` (template:
`templates/model-requirements.template.md`) records desired outputs and units,
the functional-unit relationship, inputs required by each output, supplied vs.
still-needed inputs, intended formulas when known, scenario/comparison
relationships, modeling assumptions and unresolved dependencies, and the explicit
V1 stop. For comparisons use one project-level `model-requirements.md`; option
folders hold option-specific `scope.md` and `data-requirements.md`.

Compile the schema per option with `prompts/stage0-schema-compile.md`. The schema
is **numeric-only**: every cell ends with one finite numeric value; JSON/TEXT
parameters are rejected. Keep categories, structured data, and notes in the
documents, not in cells.

## Step 7 — Review and approve

Run the schema/compatibility reviewer subagent; correct mechanical problems
before the gate. Show a concise document summary, assumptions and exclusions,
required input categories, extracted user-value counts and uncertain
interpretations, fixed inputs, and links to the full documents and
`user-inputs.csv`. Both modes require explicit approval of all three documents.
On approval: `approve --type starting_documents` (hashes + locks mode) and
`snapshot --label starting-documents`.

## Default completeness checklist

Not a rigid questionnaire — derive what's available, ask only consequential gaps,
allow overrides unless they break a hard schema/pipeline contract:

- Decision or question to support.
- Single system or comparison.
- System boundary.
- Functional unit.
- Geography, time, currency, and cost basis.
- Desired model outputs.
- Available documents and values.
- Known constraints.
