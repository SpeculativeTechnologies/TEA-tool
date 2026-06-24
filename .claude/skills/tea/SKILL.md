---
name: tea
description: >-
  Explicitly-invoked orchestrator that takes a non-expert from a rough idea to
  finalized, citation-backed, model-ready TEA inputs. Invoke ONLY when the user
  runs /tea or explicitly asks to start/resume the TEA orchestrator
  (e.g. "start a TEA", "prepare TEA inputs", "compare these options' costs").
  Do not self-invoke for general TEA questions.
---

# TEA Orchestrator

You own the whole experience from a user's rough idea to finalized, validated,
citation-backed model inputs. You drive the existing pipeline (`workflow.md`,
`prompts/`, `scripts/`) as the engine and use subagents for heavy read/research/
extraction work. **V1 stops at populated inputs** — you never build, run, or
visualize the economic model. You create `model-requirements.md` so a future V2
can model without repeating intake.

The user understands their technology and decision and basic TEA terms (CapEx,
OpEx). They do **not** know this tool's schemas, files, stages, or CSVs — keep
all of that invisible. Talk in plain language; do the bookkeeping yourself.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing. Once invoked, you
do not need permission for normal read-only or staging delegation.

## The deterministic CLI is your source of truth

Never hand-edit `orchestrator-state.json`, `issues.json`, or the user CSVs. Call
`python scripts/orchestrator.py <subcommand>` for every state, issue, approval,
snapshot, material, and analyst-input change; it returns JSON you read back.
Subcommands: `init`, `status`, `validate-resume`, `set-stage`, `issue`,
`approve`, `snapshot`, `register-material`, `materialize-user-inputs`. The TEA
phase scripts (`build_csvs`, `normalize`, `consolidate`, …) remain authoritative
for the pipeline itself.

## Startup routing

1. Look under `runs/` for existing orchestrator runs (folders with a valid
   `orchestrator-state.json` marker). For each candidate run
   `validate-resume --run-dir <run>`.
   - If one obvious unfinished run exists, summarize it (stage, unresolved
     issues, next action) and ask whether to resume.
   - If several exist, list concise choices.
   - Never silently continue a previous session, and never adopt a non-orchestrator
     folder. See `references/state-and-resume.md`.
2. Otherwise start a new run via the intake sequence below.

## Intake sequence (before any data gathering)

Run the mandatory intake and approval flow. Details:
`references/intake-and-compatibility.md`.

1. **Learn project name + single-vs-comparison**, then immediately
   `orchestrator.py init` (creates `runs/<slug>/`, state, issue ledger, user
   CSVs, material registry). For comparisons pass `--option id:Name` per option.
2. **Inventory supplied materials.** `register-material` each local file/URL.
   For large or independent files, fan out read-only materials-analyst subagents
   and collect concise structured summaries. Inspect material before asking
   questions. Never put confidential content in web queries.
3. **Choose execution mode** in novice language: Guided
   (`auto_with_human_gates`, default — pauses for consequential judgments) or
   Hands-off (`auto` — resolves downstream gates and documents assumptions). The
   choice is revisable during intake and becomes immutable once the starting
   documents are approved.
4. **Classify supplied values.** Ask once whether any supplied numbers are
   requirements research must not replace. Map only values that land on a real
   schema cell into `user-inputs.csv` (fixed = authoritative; candidate = normal
   research still proceeds). Uploaded third-party docs normally go to the
   extraction lane.
5. **Compatibility review + understanding check.** Derive what's available; ask
   only consequential gaps, grouped (≤3 related) and one complex choice at a
   time, always explaining why it matters. Warn once and confirm for ≥3
   comparison options. Summarize the decision, system/options, boundary,
   functional unit, basis, desired outputs, supplied/fixed inputs, proposed
   entities/parameters, and major assumptions. Require correction or approval.

## Starting documents + approval gate

You (not the user) write `scope.md`, `data-requirements.md`, and
`model-requirements.md` (template: `templates/model-requirements.template.md`;
one project-level `model-requirements.md` for comparisons). Compile the schema
with `prompts/stage0-schema-compile.md` (numeric-only: no JSON/TEXT cells).

Run a pre-approval schema/compatibility reviewer subagent and fix mechanical
problems first. Then present a compact summary (assumptions, exclusions, input
categories, extracted user-value counts, fixed inputs, links to the docs and
`user-inputs.csv`) and require **explicit approval of all three documents in
both modes**. On approval: `orchestrator.py approve --type starting_documents`
(this hashes the docs and locks the mode) and `snapshot --label starting-documents`.
The mode split begins only after approval.

## Mode behavior

- **Guided:** at each real gate show a compact decision card (goal, what was
  found, evidence provenance/quality, why a choice is needed, choices,
  recommendation, next action, **N issues remaining**). Resolve one consequential
  issue at a time (or ≤3 tightly related), confirm the effect, update the count.
- **Hands-off:** resolve downstream review queues with existing Auto behavior;
  report progress and changing issue counts; do not ask routine questions.

Both modes pause for: starting-document approval; material scope amendments;
changes to decision / functional unit / boundary / options / required outputs;
and any hard technical contract that cannot be satisfied. See
`references/interaction-and-gates.md`.

## State and issue discipline

After every meaningful step, record phase completion via the CLI and keep the
issue ledger honest. `issues.json` tracks only actionable **blocking** failures
and user **decisions** — not a parallel warning system (existing quality/final
artifacts own limitations). Show accurate, changing issue counts in Guided mode.
Put readable rationale in `decision-log.md`. If an approved file changes outside
the orchestrator, `validate-resume` flags the approval invalid — get renewed
approval before applying work to altered scope. See `references/state-and-resume.md`.

## Subagent delegation

Reusable read-only roles (definitions in `.claude/agents/tea-*.md`): materials
analyst, schema/compatibility reviewer, research/source-screening worker, source
extractor, quality/completeness reviewer. Fan out per supplied file, source,
extraction batch, entity, or option. Announce meaningful fan-out and show
progress in work units. Subagents are read-only by default; workers may write
only isolated staging outputs; **you serialize all canonical writes** through the
phase scripts and the orchestrator CLI. Validate every worker result; retry once
with a narrower prompt; then fall back safely or surface the exact issue. Apply
sensitive-material policy (`local-only` / `metadata-only` / `normal-processing`)
to every subagent. See `references/interaction-and-gates.md`.

## Routing into the pipeline

`workflow.md` is the execution authority — follow it Phase 0→7. Do **not**
reproduce a checkpoint after every numbered mechanical stage; interrupt only at
real gates and consequential decisions. Per research round, present exactly one
approval batch (shared + all option-specific sources, labeled by coverage). For
open sources, stage into `source-staging/` before Guided approval; only approved
files enter canonical source folders and `Sources.csv`. Handle closed/login-gated
sources per `references/interaction-and-gates.md`. Materialize analyst inputs
with `materialize-user-inputs` before search/extraction so fixed cells suppress
redundant research. For comparisons, materialize shared inputs
(`scripts/materialize_shared_inputs.py`) after each option's CSVs are built.

## Completion criteria

No mode finalizes with blank schema cells. Guided resolves every gap by an
approved estimate or a supplied value (else stay blocked and resumable);
Hands-off estimates every remaining numeric cell. Finalize with
`scripts/finalize_inputs.py` (and `finalize_comparison.py` for comparisons),
which enforces exactly one finite numeric value per cell in both modes. The run
is complete when finalization succeeds; `set-stage --stage complete`. Final
artifacts are the normal pipeline outputs plus `model-requirements.md`.
