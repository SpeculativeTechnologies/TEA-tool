# Intake and compatibility

Detailed contract for the mandatory intake and approval flow of `/tea-scope`
(Skill 1 of three). The skill body gives the sequence; this is the substance.
Keep schemas, files, and CSVs invisible to the user — derive what you can, and
resolve ambiguity by asking from your own knowledge rather than researching.

Execution mode (Guided vs. Hands-off) is **not** chosen here; it is selected and
locked at the start of `/tea-data` (Skill 3), because it only governs the
data-acquisition gates. `/tea-scope` is interactive regardless.

## Step 1 — Initialize early

After you know the project name and whether it is a single run or a comparison:

```
python scripts/orchestrator.py init --name "<name>" [--type single|comparison] \
    [--option <id>:"<display>" ...]
```

Do **not** pass `--mode` here — mode is chosen later, at the start of `/tea-data`.

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

## Step 2 — Question-driven scoping (ask, don't research)

Reaching a correct scope is the heart of this stage. When the user is vague,
**resolve ambiguity by asking, not by researching.** Draw on your own domain
knowledge to propose framing and interrogate the plan, in the spirit of a
relentless design interview.

- Ask **one question at a time** — roughly **10–15** over the stage — walking each
  branch of the decision tree and resolving dependencies in order. Do not dump a
  long questionnaire at once.
- For **every** question, give your **recommended answer** and a one-line why, so a
  non-expert can simply confirm or correct.
- Prefer your own knowledge and the **user-supplied** materials over the web. If a
  question can be answered by inspecting a supplied file, do that instead of
  asking. Run a light, targeted web search **only** when you are genuinely stuck on
  a specific factual point a question cannot resolve — never open-ended research.
- Cover the completeness checklist below through these questions: the decision,
  single-vs-comparison, system boundary, functional unit, basis
  (geography/time/currency), desired outputs, supplied/fixed values, proposed
  entities/parameters, and major assumptions.

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

Default to your own knowledge and to questions (Step 2); reserve web search for a
specific factual point a question cannot resolve. Distinguish user-confirmed
system definitions from public facts and unresolved placeholders. Any numeric
evidence found this way must later enter the normal evidence pipeline. For three
or more comparison options, warn once that research volume, review burden, and
comparability risk increase, then require confirmation.

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
relationships, and modeling assumptions and unresolved dependencies. It is the
**specification `/tea-model` implements** as a runnable `model.py`, so make the
outputs and their formulas explicit and numeric. For comparisons use one
project-level `model-requirements.md`; option folders hold option-specific
`scope.md` and `data-requirements.md`.

Compile the schema per option with `prompts/stage0-schema-compile.md`. The schema
is **numeric-only**: every cell ends with one finite numeric value; JSON/TEXT
parameters are rejected. Keep categories, structured data, and notes in the
documents, not in cells.

## Step 7 — Review and approve

Run the schema/compatibility reviewer subagent; correct mechanical problems
before the gate. Show a concise document summary, assumptions and exclusions,
required input categories, extracted user-value counts and uncertain
interpretations, fixed inputs, and links to the full documents and
`user-inputs.csv`. Require explicit approval of all three documents. On approval:
`approve --type starting_documents` (hashes the three documents) and
`snapshot --label starting-documents`, then direct the user to run `/tea-model`.

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
