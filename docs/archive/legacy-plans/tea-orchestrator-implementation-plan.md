# New-User TEA Orchestrator — V1 Implementation Plan

> **Superseded implementation plan.** This document describes the earlier
> single-skill, inputs-only design. The shipping workflow uses `/tea-scope`,
> `/tea-model`, `/tea-data`, and `/tea-insights`, including model construction
> and execution. See [SETUP.md](../../../SETUP.md) and
> [README-tea-skills.md](../../../README-tea-skills.md) for current guidance.

## 1. Decision

Build V1 as an explicitly invoked, repo-scoped Codex skill:

```text
$tea-orchestrator
```

The skill owns the full experience from rough user idea through finalized,
model-ready TEA inputs. It uses the existing workflow, prompts, and scripts as
the execution engine, and uses subagents for bounded, context-heavy work.

Start with:

- `.agents/skills/tea-orchestrator/` for the user-facing workflow.
- `.codex/agents/` for reusable specialist agent definitions.
- A small deterministic orchestration CLI for state, issues, approvals, resume,
  supplied inputs, and approval-safe materialization.

After repo testing, package the skill and agent configuration as an installable
plugin. Do not build a custom OpenAI API application for V1.

## 2. Product Boundary

V1 ends with complete, validated, citation-backed model inputs.

It does not build, execute, or visualize the economic model. It creates
`model-requirements.md` so a future V2 can add modeling and visualization
without repeating intake.

Every final schema cell must contain exactly one finite numeric value. Text,
categories, booleans, and structured context remain in the starting documents,
notes, and scenario definitions rather than becoming model-input cells.

## 3. User Contract

### Invocation

- Explicit invocation only.
- Disable implicit skill invocation.
- One visible skill; internal agents and workflow prompts are implementation
  details.

### Assumed user knowledge

Assume the user:

- Understands their technology, project, and decision context.
- Knows basic TEA language such as CapEx and OpEx.
- Does not know this tool's schemas, files, stages, or data contracts.

### Starting material

Accept any mixture of:

- Plain-language descriptions and conversational answers.
- Local documents, PDFs, and spreadsheets.
- Existing models and formulas.
- URLs.
- User-supplied values and assumptions.

Inspect supplied material before asking questions. For large or independent
files, fan out read-only materials-analysis subagents and collect concise,
structured summaries.

Existing models and spreadsheets may define both required inputs and supplied
values. Inspect formulas, assumptions, units, and outputs, but do not modify or
execute a supplied model unless the user separately requests it.

### Required framing

The default completeness checklist is:

- Decision or question to support.
- Single system or comparison.
- System boundary.
- Functional unit.
- Geography, time, currency, and cost basis.
- Desired model outputs.
- Available documents and values.
- Known constraints.

This is not a rigid questionnaire. Derive what is already available, ask only
for consequential gaps, and allow user overrides unless they violate a hard
schema or pipeline contract.

Use the standard A–E quality definitions unless the user explicitly requests a
custom scheme. Infer proposed estimation policies from the calculation
structure and parameter types; ask only when the choice would materially change
the result. Validation targets remain optional.

### Question behavior

- Ask focused questions in plain language.
- Group up to three tightly related questions.
- Ask complex choices one at a time.
- Explain why missing information matters.
- Never silently invent units, denominator, scale, currency year, geography,
  scenario, or measured-versus-assumed status.
- When input is incompatible, explain the mismatch, propose the smallest viable
  correction, and allow a documented methodological override when technically
  valid.

## 4. Mandatory Intake And Approval Flow

### Step 1: Initialize early

After learning the project name and whether it is a single run or comparison:

- Create `runs/<project-slug>/`.
- Generate stable project and option IDs.
- Mark state as `intake`.
- Inventory supplied materials.
- Begin persisting confirmed facts.

If the slug already exists:

- Offer resume only when it contains a valid unfinished orchestrator marker.
- Otherwise generate a suffixed slug or request a different name.
- Never merge into an unknown folder.

V1 does not adopt pre-existing TEA runs.

Copy trusted local inputs into `provided-materials/` when practical, preserving
original filenames. Record original paths or URLs, checksums, handling policy,
and copy-versus-reference status in `provided-materials.json`. Permit
reference-only registration for very large or sensitive files.

### Step 2: Choose execution mode

Ask early, in novice-facing language:

- **Guided mode** (`auto_with_human_gates`): pauses for consequential
  judgments.
- **Hands-off mode** (`auto`): resolves downstream gates automatically and
  documents assumptions.

Guided is the default. The user may revise the choice during intake. The choice
becomes immutable when the starting documents are approved; changing it later
requires a new run.

### Step 3: Inspect and classify supplied values

Ask once:

> Are any supplied numbers requirements or assumptions that research must not
> replace?

Classify mapped values as:

- **Fixed input:** authoritative unless the user explicitly changes it.
- **Candidate evidence:** retained, but normal research still proceeds.

Uploaded third-party documents normally enter the extraction lane, not the
analyst-input lane. The user may fix selected extracted values; fixed status is
per target cell, never per whole document.

Only values mapped to a proposed schema cell enter `user-inputs.csv`. If a value
cannot be mapped, explain why and offer a valid schema change. Discard it as a
pipeline input if the user declines the mapping or confirms it is irrelevant.

### Step 4: Compatibility review

Check:

- Desired outputs can be supported by the proposed inputs.
- Comparison options provide an equivalent function.
- The functional unit is measurable.
- Boundaries and geography/time/currency bases are coherent.
- Proposed parameters support desired outputs.
- Supplied values have interpretable units and bases.
- Materially different scenarios are not collapsed into one run.

Blocking failures pause intake. Nonblocking uncertainties appear as assumptions
in the understanding check. Methodological overrides are allowed and recorded;
mechanically invalid configurations are not.

Limited research during intake may inform proposed framing choices. Distinguish
user-confirmed system definitions from public facts and unresolved
placeholders. Any numeric evidence found during intake must later enter the
normal evidence pipeline.

For three or more comparison options, warn once that research volume, review
burden, and comparability risk increase, then require confirmation.

### Step 5: Understanding check

Before creating formal documents, summarize:

- The decision.
- The system or options.
- The boundary.
- The functional unit.
- Basis assumptions.
- Desired outputs.
- Supplied evidence and fixed inputs.
- Proposed entities and input categories.
- Major assumptions and unresolved questions.

Require correction or approval.

### Step 6: Generate the starting documents

The orchestrator, not the user, writes:

- `scope.md`
- `data-requirements.md`
- `model-requirements.md`

`model-requirements.md` records:

- Desired outputs and units.
- Functional-unit relationship.
- Inputs required by each output.
- Supplied versus still-needed inputs.
- Intended formulas or calculation logic when known.
- Scenario and comparison relationships.
- Modeling assumptions and unresolved dependencies.
- The explicit V1 stop before model execution.

For comparisons, use one project-level `model-requirements.md`. Option folders
contain option-specific scope and data requirements.

### Step 7: Review and approve

Run a pre-approval schema/compatibility review subagent. Correct mechanical
problems before presenting the gate.

Show:

- A concise document summary.
- Assumptions and exclusions.
- Required input categories.
- Extracted user-value counts and uncertain interpretations.
- Fixed inputs.
- Links to the full documents and `user-inputs.csv`.

Both modes require explicit approval of all three starting documents. The mode
split begins only after approval.

Snapshot approved documents and record their hashes.

## 5. Durable Run State

### Required orchestrator artifacts

```text
runs/<project>/
  orchestrator-state.json
  issues.json
  decision-log.md
  intake-summary.md
  model-requirements.md
  user-inputs.csv
  user-sources.csv
  provided-materials.json
  provided-materials/
  source-staging/
  history/
```

Comparison projects keep one project-level state and issue ledger. Option
folders retain normal TEA artifacts and compact phase status only.

### `orchestrator-state.json`

Keep it concise. Store:

- Versioned orchestrator marker and repository compatibility version.
- Project ID, type, run path, and creation date.
- Current stage and status.
- Chosen execution mode.
- Confirmed normalized intake facts.
- Current workflow phase per run/option.
- Approval records and artifact hashes.
- Aggregate unresolved issue count and next issue ID.
- Active blockers and next safe action.
- Limited subagent job status needed for the current turn only.

Do not store the chat transcript.

Use the compact stages:

```text
intake
understanding_review
starting_documents_review
schema_setup
evidence_collection
extraction
normalization_and_selection
completeness_review
estimation
finalization
complete
```

### `issues.json`

Track only actionable blockers and user decisions. Do not create a parallel
warning system; existing quality and final-review artifacts own limitations.

Each issue has:

- Stable ID.
- Category: `blocking` or `decision`.
- Status.
- Affected artifact, option, entity, parameter, or source.
- Plain-language question.
- Recommended resolution.
- Resolution metadata.

Retain resolved entries compactly for counter integrity. Put readable rationale
in `decision-log.md`.

### Approval integrity

For each meaningful approval, store:

- Approval type and stage.
- Date.
- Artifact hashes.
- Relevant issue IDs.

If approved files change outside the orchestrator, invalidate the approval and
require renewed approval. Preserve completed work, but do not silently apply it
to altered scope.

Snapshot only meaningful semantic boundaries:

```text
history/<timestamp>-starting-documents/
history/<timestamp>-scope-amendment/
```

Do not version routine pipeline CSV changes.

### Resume behavior

- If one unfinished orchestrator run is obvious, summarize it and ask to resume.
- If several exist, list concise choices.
- Never silently continue commands from a previous session.
- Validate the marker, artifact hashes, issue ledger, and expected workflow
  artifacts before choosing the next safe action.

## 6. User-Supplied Input Contract

### New CSVs

`user-sources.csv` uses the source registry shape and permits
`source_role=analyst`.

`user-inputs.csv` contains mapped values only, including:

- Stable input ID.
- Target entity and parameter.
- Raw value and units.
- Basis scale, basis units, and basis year.
- Source key and precise reference.
- Quality tag.
- Input classification.
- Fixed status.
- Notes and user rationale.

One synthetic analyst source may cover a coherent conversational submission
batch. Uploaded documents use their real document provenance and precise
sheet/cell, page, table, or decision-log references.

### Pipeline materialization

Add `input_priority` to `Audit.csv` and `Main Input.csv`:

- `fixed`
- blank

Only validated user decisions may set `fixed`.

Selection precedence becomes:

1. Fixed candidate, regardless of origin.
2. Approved shared comparison input.
3. Ordinary candidates under existing quality, scope-fit, recency, and
   disagreement rules.

Two conflicting fixed candidates for one cell create a blocking issue in both
modes.

Other rules:

- Fixed inputs suppress replacement research.
- Candidate analyst evidence never suppresses normal research.
- Uploaded third-party evidence uses `input_origin=extracted`.
- Direct user assertions or model assumptions use `input_origin=analyst`.
- Fixed shared assumptions use `input_origin=shared` and
  `input_priority=fixed`.
- Contrary evidence may be recorded, but cannot replace a fixed input without
  explicit user approval.

## 7. Orchestration CLI

Add one small deterministic entry point, tentatively:

```text
scripts/orchestrator.py
```

Keep the user-facing experience natural language; the skill calls these
subcommands internally:

- `init`
- `status`
- `validate-resume`
- `issue`
- `approve`
- `snapshot`
- `register-material`
- `materialize-user-inputs`

Responsibilities:

- Initialize idempotent run structures.
- Validate state and issue schemas.
- Enforce legal state transitions.
- Maintain issue counters.
- Hash and verify approved artifacts.
- Create semantic snapshots.
- Validate and materialize analyst inputs.
- Detect fixed-input conflicts.
- Emit concise machine-readable summaries for the skill.

Do not move the existing TEA workflow into this CLI. Existing phase scripts
remain authoritative.

## 8. Skill Structure

```text
.agents/skills/tea-orchestrator/
  SKILL.md
  agents/openai.yaml
  references/
    intake-and-compatibility.md
    interaction-and-gates.md
    state-and-resume.md
```

`SKILL.md` should remain lean and contain:

- Explicit invocation requirement.
- Startup and resume routing.
- Intake sequence.
- Mandatory understanding and document approvals.
- Mode behavior.
- State and issue discipline.
- Subagent delegation rules.
- Routing into `workflow.md`.
- Completion criteria.

Detailed contracts belong in references or the repository's existing
authoritative files. Do not copy `workflow.md`, prompts, or templates into the
repo-scoped prototype.

Configure `agents/openai.yaml` with:

```yaml
policy:
  allow_implicit_invocation: false
```

## 9. Subagent Model

Define a small set of reusable roles, without limiting worker count:

- Materials analyst.
- Schema/compatibility reviewer.
- Research/source-screening worker.
- Source extractor.
- Quality/completeness reviewer.

Fan out ephemeral workers per:

- Supplied file or model.
- Source.
- Extraction batch.
- Entity.
- Comparison option.
- Workflow-defined estimation unit.

Rules:

- Announce meaningful fan-out and show progress in work units.
- Do not request permission for normal read-only or staging delegation after
  explicit skill invocation.
- Honor explicit user direction about worker count or one-worker-per-source
  fan-out when it remains safe and bounded.
- Subagents are read-only by default.
- Workers may write only isolated staging outputs when the existing workflow
  requires file outputs.
- The main orchestrator serializes canonical writes.
- Validate every worker result contract.
- Retry an invalid or failed result once with a narrower prompt.
- Then use a safe fallback or expose the exact unresolved issue.
- Do not persist exploratory subagent summaries as a separate audit system.

Sensitive-material policies apply to every subagent:

- `local-only`
- `metadata-only`
- `normal-processing`

Never include confidential content in web search queries.

## 10. Workflow Integration

### General

Follow `workflow.md` as the execution authority. Do not reproduce the smoke-test
guide's approval after every numbered mechanical stage.

Record all phase completion in state. Interrupt the user only at real gates or
consequential decisions.

### Guided mode

At a gate, show a compact decision card:

- Current goal.
- What was found.
- Evidence provenance and quality.
- Why a choice is needed.
- Available choices.
- Recommendation.
- Next action.
- **N issues remaining.**

Show the complete issue count, then resolve one consequential issue at a time,
or up to three tightly related issues. Confirm the effect and update the count
after each response.

### Hands-off mode

Resolve downstream review queues with existing Auto behavior. Report progress
and changing issue counts, but do not ask routine questions.

Both modes pause for:

- Starting-document approval.
- Material scope amendments.
- Changes to decision, functional unit, boundary, options, or required outputs.
- A hard technical contract that cannot be satisfied.

For bounded scope amendments, snapshot the old state, assess which downstream
artifacts are invalid, obtain approval, and rerun only affected stages.
Recommend a new run when the core decision, functional unit, or system identity
changes substantially.

### Source handling

For each workflow research round:

- Fan out shared and option-specific searches as appropriate.
- Present exactly one approval batch containing shared and all option-specific
  sources, labeled by coverage.
- For open sources, download into `source-staging/` before Guided approval.
- Only approved files enter canonical source folders and `Sources.csv`.
- Rejected staged files remain ignored or are removed safely.
- A rejection does not automatically trigger another search; follow normal
  gap-fill, completeness, and estimation routing.

In Guided mode:

- Provide links for closed/login-gated sources and explain what the user should
  obtain.
- Retrieval is optional.
- If requested, fan out a focused open-access substitution search.
- If no credible substitute exists, keep the cell empty until estimation or
  user supply.

In Hands-off mode:

- Do not ask the user to retrieve closed sources.
- Search for the best open substitute.
- If none exists, proceed to estimation.

Quarantine risky or unsupported files. Never execute embedded content. Seek a
safe PDF, CSV, or plain-text representation.

### Comparisons

- Support two or more options.
- Warn and confirm once for three or more.
- Require functional equivalence, not identical schemas.
- Search shared assumptions first, then fan out option-specific research.
- Present shared and option sources together in one approval batch per round.
- Adding or removing an option after approval is a mandatory scope amendment.

### Completeness and finalization

No mode may finalize with blank schema cells.

In Guided mode, every remaining gap must be resolved by:

- Approving an estimate, or
- Supplying a value.

If neither is available, keep the run blocked and resumable.

Hands-off mode estimates every remaining numeric cell under the current Auto
contract.

Finalization validates exactly one finite numeric model value per schema cell
for both modes.

## 11. Required Pipeline Changes

Modify the existing contracts carefully because the working tree already
contains active workflow changes.

### CSV and selection changes

- Add `input_priority` to Audit and Main Input schemas.
- Permit `analyst` in source-role validation.
- Add deterministic analyst-input materialization.
- Implement fixed precedence and fixed-conflict validation.
- Ensure non-fixed analyst evidence does not mark a search cell satisfied.
- Permit fixed status on shared inputs and selected extracted values.

### Schema changes

- Reject `JSON` and `TEXT` parameters in both execution modes.
- Keep contextual text in documents and notes.
- Require numeric final cells regardless of mode.

### Finalization changes

- Generalize the current Auto completeness check to all modes.
- Require exactly one finite numeric value per schema cell.
- Keep Guided runs blocked until estimates or user values resolve all gaps.

### Prompt and workflow changes

- Update Stage 0 to consume approved `model-requirements.md`.
- Make the schema compiler numeric-only.
- Document analyst inputs, fixed inputs, and research suppression rules.
- Add the novice-orchestration layer without duplicating detailed phase logic.

## 12. Implementation Sequence

### Phase A — Deterministic contracts

1. Add state and issue schemas/helpers.
2. Add orchestration CLI initialization, status, issue, approval, and resume
   validation.
3. Extend CSV contracts with `input_priority` and `analyst` source role.
4. Add `user-inputs.csv` and `user-sources.csv` validation/materialization.
5. Implement fixed precedence and conflict behavior.
6. Enforce numeric-only schemas and no-gap finalization in both modes.

This phase should land before the conversational skill so the skill never has
to maintain fragile JSON/CSV contracts itself.

### Phase B — Starting documents and intake

1. Add `model-requirements.md` template.
2. Update Stage 0 compilation guidance.
3. Implement supplied-material inventory and approval snapshots.
4. Define the compatibility checklist and understanding-check contract.

### Phase C — Skill and subagents

1. Initialize the repo-scoped skill with `skill-creator`.
2. Write concise `SKILL.md` and focused references.
3. Add explicit-only UI metadata.
4. Add project-scoped specialist agent definitions.
5. Route all canonical writes through the main orchestrator and helper CLI.

### Phase D — Workflow UX

1. Add Guided decision-card behavior and issue counters.
2. Add Hands-off progress behavior.
3. Add one-batch-per-round source approval.
4. Add open/closed source handling and staging.
5. Add comparison fan-out and project-level progress summaries.
6. Add semantic scope-amendment invalidation and rerun planning.

### Phase E — Validation and iteration

1. Run deterministic tests.
2. Run scenario-based skill evaluations.
3. Forward-test the skill with fresh subagents and minimal leaked context.
4. Refine instructions based on observed failures.
5. Package as a plugin only after repo-scoped behavior is stable.

## 13. Tests And Evaluations

### Deterministic tests

Add tests for:

- Initialization and valid orchestrator marker.
- Unknown-folder refusal.
- State transitions and concise status.
- Issue creation, resolution, and counters.
- Approval hashing and invalidation after file edits.
- Resume validation.
- Snapshot creation.
- Analyst-source registration.
- User-input mapping and materialization.
- Fixed-input precedence.
- Conflicting fixed inputs.
- Fixed shared inputs.
- Candidate analyst evidence not suppressing search.
- Uploaded third-party evidence retaining extraction origin.
- Numeric-only schema validation in both modes.
- No-gap finalization in both modes.
- Multi-option comparison state.

### Skill evaluations

Evaluate behavior, decisions, and artifacts rather than exact wording.

#### Comparison happy path

Adapt LED versus incandescent:

- Novice-style initial request.
- Partial user-supplied data.
- One fixed assumption.
- Shared electricity input.
- Adaptive intake.
- Comparison compatibility check.
- Starting-document approval.
- One source batch.
- Issue counter changes.
- Interrupted and resumed execution.
- Complete final inputs.

#### Standalone model-inspection path

Adapt the managed-compute-service example:

- Small workbook fixture with formulas and assumptions.
- One value missing units.
- Derive required inputs from formulas.
- Separate fixed model assumptions from uploaded third-party evidence.
- Ask the missing-unit question.
- Produce and approve all three starting documents.
- Complete the normal workflow.

#### Adversarial cases

- Different functional units across comparison options.
- Three-option warning and override.
- Closed source unavailable; user requests open substitute.
- Rejected source flows forward without an automatic research loop.
- Fixed input conflicts with research.
- Two fixed inputs conflict.
- Approved document changed outside the orchestrator.
- Material scope amendment mid-run.
- Subagent timeout and invalid return.
- Sensitive local-only material.
- Guided run with a final blank remains blocked.

## 14. V1 Acceptance Criteria

V1 is ready when:

- A novice can start with `$tea-orchestrator` and plain-language context.
- The orchestrator creates and resumes only its own runs.
- Intake is adaptive and does not require users to fill templates.
- Both modes require understanding and starting-document approval.
- The mode becomes fixed after approval.
- Supplied values preserve provenance, basis, and fixed status.
- Fixed values cannot be silently displaced.
- Subagents handle large read/research/extraction workloads without owning
  canonical writes.
- Guided mode shows accurate changing issue counts.
- Research and source approval follow the existing workflow.
- Comparison projects support shared inputs and multi-option fan-out.
- Every finalized schema cell contains one finite numeric value.
- Final artifacts remain the current TEA pipeline outputs plus
  `model-requirements.md`.
- The two primary scenario evaluations pass after interruption and resume.

## 15. Explicitly Deferred To V2

- Economic model generation.
- Model execution.
- Sensitivity and uncertainty analysis.
- Visualization and dashboards.
- Automated output calculation.
- Adoption of legacy runs.
- Custom API application or standalone web UI.
- Plugin distribution before the repo-scoped workflow is proven.
