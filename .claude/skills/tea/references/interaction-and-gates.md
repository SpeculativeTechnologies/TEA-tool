# Interaction, gates, and subagents

How to run `workflow.md` for a non-expert: when to interrupt, what a gate looks
like, how sources and comparisons are handled, and the subagent contract.

## General

Follow `workflow.md` as the execution authority. Do **not** reproduce a
checkpoint after every numbered mechanical stage. Record phase completion in
state (`set-stage`, and per-option phase notes for comparisons). Interrupt the
user only at real gates or consequential decisions.

Both modes pause for:

- Starting-document approval.
- Material scope amendments.
- Changes to decision, functional unit, boundary, options, or required outputs.
- A hard technical contract that cannot be satisfied.

## Guided mode — decision cards

At a gate, show a compact card:

- **Goal** — what this stage is for, in one plain sentence.
- **What was found** — key values, sources, files, gaps, or script results.
- **Evidence** — provenance and quality of what you found.
- **Why a choice is needed.**
- **Choices** — the available options.
- **Recommendation** — your default and why.
- **Next action** — the one next numbered stage if approved.
- **N issues remaining.**

Show the complete issue count, then resolve one consequential issue at a time
(or up to three tightly related). Confirm the effect and update the count after
each response. Keep the user out of raw research: present source title,
publisher, URL, candidate values, and your recommendation — never ask them to
find facts manually.

## Hands-off mode — progress

Resolve downstream review queues with the existing Auto behavior
(`prompts/auto-gate-agent.md`, `auto-run-log.md`). Report progress and changing
issue counts; do not ask routine questions. Ordinary ambiguity is not a reason
to interrupt. Still pause for the four shared pause conditions above.

## Source handling (per research round)

- Fan out shared and option-specific searches as appropriate.
- Present **exactly one approval batch** containing shared and all
  option-specific sources, labeled by coverage.
- For open sources, download into `source-staging/` before Guided approval.
- Only approved files enter canonical source folders and `Sources.csv`.
- Rejected staged files stay ignored or are removed safely. A rejection does not
  auto-trigger another search; follow normal gap-fill / completeness / estimation
  routing.

Guided, closed/login-gated sources: provide links and explain what to obtain;
retrieval is optional. If asked, fan out a focused open-access substitution
search. If no credible substitute exists, leave the cell empty until estimation
or user supply. Hands-off: do not ask the user to retrieve closed sources; search
for the best open substitute; if none exists, proceed to estimation.

Quarantine risky or unsupported files. Never execute embedded content. Seek a
safe PDF, CSV, or plain-text representation.

## Analyst inputs and fixed precedence

Materialize analyst inputs **before** search/extraction so fixed cells suppress
redundant research:

```
python scripts/orchestrator.py materialize-user-inputs --run-dir RUN
```

This validates `user-inputs.csv`/`user-sources.csv` against the schema, blocks on
two disagreeing fixed inputs for one cell, merges sources into `Sources.csv`
(allowing `source_role=analyst`), and writes analyst Audit rows (origin +
`input_priority=fixed` when fixed). Selection precedence at consolidation:
(1) fixed candidate, any origin; (2) approved shared input; (3) ordinary
candidates under quality/scope-fit/recency/disagreement rules. Candidate
(non-fixed) analyst evidence never suppresses research and never marks a search
cell satisfied. Contrary evidence may be recorded but cannot displace a fixed
input without explicit user approval.

## Comparisons

- Support two or more options; warn and confirm once for three or more.
- Require functional equivalence, not identical schemas.
- Search shared assumptions first, then fan out option-specific research.
- Present shared and option sources together in one approval batch per round.
- Materialize shared inputs with `scripts/materialize_shared_inputs.py
  --project-dir <project>` after each option's CSVs are built; search,
  extraction, and estimation skip cells already satisfied by `input_origin=shared`.
- Adding or removing an option after approval is a mandatory scope amendment.
- Keep one project-level state and issue ledger; option folders hold normal TEA
  artifacts and compact phase status.

## Scope amendments

For a bounded amendment: `snapshot --label scope-amendment` the old state, assess
which downstream artifacts are invalid, obtain approval, and rerun only the
affected stages (rewind with `set-stage`). Recommend a **new run** when the core
decision, functional unit, or system identity changes substantially.

## Completeness and finalization

No mode may finalize with blank schema cells. Guided: every remaining gap must be
resolved by approving an estimate or supplying a value; if neither is available,
keep the run blocked and resumable. Hands-off: estimate every remaining numeric
cell under the Auto contract. `finalize_inputs.py` validates exactly one finite
numeric model value per cell in both modes (use `--allow-gaps` only for an
explicitly-draft intermediate manifest, never the final hand-off).

## Subagent contract

Reusable roles (`.claude/agents/tea-*.md`): materials analyst, schema/compatibility
reviewer, research/source-screening worker, source extractor, quality/completeness
reviewer. Fan out ephemeral workers per supplied file/model, source, extraction
batch, entity, comparison option, or workflow-defined estimation unit.

- Announce meaningful fan-out; show progress in work units.
- After explicit invocation, do not ask permission for normal read-only or
  staging delegation.
- Honor explicit user direction about worker count / one-worker-per-source when
  safe and bounded.
- Subagents are **read-only by default**; workers may write only isolated staging
  outputs when the workflow requires file outputs. The main orchestrator
  serializes all canonical writes (phase scripts + orchestrator CLI).
- Validate every worker result contract. Retry an invalid/failed result once with
  a narrower prompt; then use a safe fallback or surface the exact unresolved
  issue. Do not persist exploratory subagent summaries as a separate audit system.

Sensitive-material policy applies to every subagent: `local-only` (never leaves
the machine), `metadata-only` (only metadata may be processed/shared), or
`normal-processing`. **Never include confidential content in web search queries.**
