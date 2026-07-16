# Intake and compatibility

Detailed contract for the mandatory intake and approval flow of `/tea-scope`
(Skill 1 of four). The skill body gives the sequence; this is the substance.
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

- Ask **one question at a time**, walking each branch of the decision tree and
  resolving dependencies in order. Do not dump a long questionnaire at once. Give
  the user an **up-front estimate** (~12 questions) so the interview feels bounded,
  but the real rule is **ask until the scope is unambiguous**: if open branches
  remain when you reach the estimate, tell the user plainly that you need a few
  more and continue (e.g. *"I'd said about a dozen — I haven't fully nailed the
  boundary yet, so let me ask 3–4 more."*). Never sacrifice a necessary question to
  hit the number.
- For **every** question, give your **recommended answer** and a one-line why, so a
  non-expert can simply confirm or correct.
- Prefer your own knowledge and the **user-supplied** materials over the web. If a
  question can be answered by inspecting a supplied file, do that instead of
  asking. Run a light, targeted web search **only** when you are genuinely stuck on
  a specific factual point a question cannot resolve — never open-ended research.
- Cover the completeness checklist below through these questions: the decision,
  single-vs-comparison, system boundary, functional unit, basis
  (geography/time/currency), desired outputs, supplied/fixed values, proposed
  entities/parameters, major assumptions, and **which external benchmarks the
  results should be validated against** (ask so "none" is a conscious choice, not
  an oversight). Capture only the metric and unit — **never a benchmark value from
  your own memory**; `/tea-data` researches the values with citations.
- **Walk the entities explicitly.** A TEA is one or more connected unit processes
  (entities), each with inputs, outputs, and optionally waste streams; a
  single-entity system is fine, and an entity may be one step or a phase bundling
  many unit operations. Decompose the system into entities, then for **each entity**
  confirm: what flows **in**, what flows **out**, any **waste stream** (and whether
  it carries a disposal cost), what it **connects to**, and the **key parameters** it
  needs. This is what lets a non-expert see what each unit contributes before
  approving.

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
types; ask only when the choice would materially change the result.

**Validation targets / benchmarks are optional, but named — never valued — here.**
Prompt the user for the external benchmarks their results should be checked against
(e.g. "published cost of Ti-6Al-4V billet, USD/kg"). Record the **metric and unit
only**. Do **not** fill in a benchmark number from your own knowledge — that would
plant an assumed value into a defensibility check. The actual values are researched
in `/tea-data` through the same citation-backed evidence rounds as every other
cell. Each named benchmark is compiled into a cell under the reserved `BENCHMARK`
entity (see `prompts/stage0-schema-compile.md`): an ordinary, audited cell that the
model **ignores as an input** and instead surfaces beside the matching computed
output. If the user names no benchmarks, mint no `BENCHMARK` entity.

## Step 5 — Understanding check

Before writing any formal document, summarize: the decision; the system or
options; the boundary; the functional unit; basis assumptions; desired outputs;
supplied evidence and fixed inputs; proposed entities and input categories;
major assumptions and unresolved questions. Require correction or approval.
Record the summary in `intake-summary.md`.

## Step 6 — Generate the starting documents

You write `scope-summary.md`, `scope.md`, `process-flow.md`,
`data-requirements.md`, and `model-requirements.md` (never the user).
`scope-summary.md` (template: `templates/scope-summary.template.md`) is the
concise, human-readable "read this first" artifact for the approval moment. It is
non-authoritative: if it conflicts with the canonical documents, the canonical
documents control. It must introduce no facts, assumptions, entities, parameters,
formulas, or benchmark values absent from those documents.
`model-requirements.md` (template: `templates/model-requirements.template.md`)
records desired outputs and units,
the functional-unit relationship, inputs required by each output, supplied vs.
still-needed inputs, intended formulas when known, scenario/comparison
relationships, and modeling assumptions and unresolved dependencies. It is the
**specification `/tea-model` implements** as a runnable `model.py`, so make the
outputs and their formulas explicit and numeric. For comparisons use one
project-level `model-requirements.md`; option folders hold option-specific
`scope.md` and `data-requirements.md`.

Three communication artifacts the docs must carry so a non-expert can actually
*understand* their model — not just approve a black box:

- **Scope summary in `scope-summary.md`.** A short, decision-oriented review
  artifact covering the decision, boundary, functional unit, basis,
  options/scenarios, validation targets, the process-flow diagram, model logic,
  and highest-leverage things to check before approval. Embed the same Mermaid
  diagram that appears in `process-flow.md` so the summary can be reviewed on its
  own; `process-flow.md` remains the canonical standalone diagram. It should
  explicitly tell the user that the other generated documents are mostly working
  artifacts for the next phases of the pipeline: useful to audit, but not
  required end-to-end reading before continuing.
- **Process flow diagram in its own `process-flow.md`.** A Mermaid `flowchart`
  (template: `templates/process-flow.template.md`) with one node per entity, edges
  for the flows between them, and each node annotated with what flows **in**, what
  flows **out**, any **waste stream**, and the key data the unit needs. Build it from
  the entity decomposition; keep node labels in the user's plain vocabulary. It lives
  in its own file (linked from `scope.md` §6), and is approved and snapshotted with
  the other docs.
- **"How the model is solved" in `model-requirements.md`.** A plain-language
  walkthrough that **walks the actual entity graph** — inputs → each entity's
  contribution → aggregation across connected entities → functional-unit
  normalization → the headline number (e.g. $/kg, $/area) — plus **one worked
  example that carries a representative input all the way through to that headline
  number** (see the template section), not an isolated line item. Prefer a
  user-supplied fixed value; otherwise use clearly-labeled illustrative numbers — the
  example demonstrates the *mechanics*, and must not assert any researched value
  (benchmarks included).

Compile the schema per option with `prompts/stage0-schema-compile.md`. The schema
is **numeric-only**: every cell ends with one finite numeric value; JSON/TEXT
parameters are rejected. Keep categories, structured data, and notes in the
documents, not in cells.

## Step 7 — Review and approve

Run the schema/compatibility reviewer subagent; correct mechanical problems
before the gate. Link `scope-summary.md` first as the recommended human-readable
review artifact, and explain that the remaining generated documents are mostly
working artifacts for the next phases. Show a concise document summary,
assumptions and exclusions, required input categories, extracted user-value
counts and uncertain
interpretations, fixed inputs, **the process-flow diagram called out and linked**,
and links to the full documents and `user-inputs.csv`. **Echo, in the approval
message itself, the "how the model is solved" walkthrough and the full-path worked
example** (condensed), and **show or link the process-flow diagram**, so the user
understands how their model will be computed before they sign off — the chat
message is where the decision happens, so it must not be a black box. Require
explicit approval of all five documents. On approval:
`approve --type starting_documents` (hashes `scope-summary.md`, `scope.md`,
`process-flow.md`, `data-requirements.md`, `model-requirements.md`) and
`snapshot --label starting-documents`, then direct the user to run `/tea-model`.

## Default completeness checklist

Not a rigid questionnaire — derive what's available, ask only consequential gaps,
allow overrides unless they break a hard schema/pipeline contract:

- Decision or question to support.
- Single system or comparison.
- System boundary.
- Functional unit.
- Geography, time, currency, and cost basis.
- Entity decomposition: the connected unit processes, and for each its inputs,
  outputs, optional waste streams, key parameters, and what it connects to.
- Desired model outputs.
- Available documents and values.
- Known constraints.
