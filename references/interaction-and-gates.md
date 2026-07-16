# Interaction, gates, and subagents

The execution contract for `/tea-data` (Skill 3): how to run `workflow.md` for a
non-expert — when to interrupt, what a gate looks like, how sources and
comparisons are handled, the subagent contract, and how the finalized inputs are
handed off. `/tea-data` only starts once `model_approved` is recorded and valid
(`status` → `approvals.valid`); otherwise send the user to `/tea-model`. Running
the populated model and exploring the results is `/tea-insights` (Skill 4) — see
`references/insights-and-iteration.md`.

## General

Follow `workflow.md` as the execution authority. Do **not** reproduce a
checkpoint after every numbered mechanical stage. Record phase completion in
state (`set-stage`, and per-option phase notes for comparisons). Interrupt the
user only at real gates or consequential decisions.

Both modes pause for:

- Material scope amendments.
- Changes to decision, functional unit, boundary, options, or required outputs.
- A hard technical contract that cannot be satisfied.

(Starting-document and model approval already happened in `/tea-scope` and
`/tea-model`; touching either invalidates its approval and is handled as an
amendment.)

Research depth is fixed by the workflow, not selected at a gate. Never ask the
user to choose live research versus estimation, and never introduce a fast,
estimation-led, calibration-only, or "research one option, estimate the rest"
path. Runtime, token use, and subagent count are not consequential decisions.
Estimation is available only for residual blanks after the recorded search,
screening, extraction, normalization, and completeness stages.

## Mode selection (start of /tea-data)

`/tea-data` begins by asking the user, in novice language, how to run the data
hunt:

- **Guided** (`auto_with_human_gates`, default): pauses at consequential gates.
- **Hands-off** (`auto`): resolves downstream gates automatically and documents
  assumptions.

Record and lock the choice before any acquisition work:

```
python scripts/orchestrator.py set-mode --run-dir RUN \
    --mode auto_with_human_gates|auto --lock
```

The mode is immutable once locked (changing it requires a new run) and governs
only the gate behavior in the stages below.

Auto is an interaction policy, not permission to skip work. In Hands-off mode,
resolve gates without the user while preserving the same research-first stage
sequence and provenance requirements as Guided mode.

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

- Use `tea-research-screener` to produce candidate JSON only. Do not ask a
  general-purpose worker to search and return final values for every cell.
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

Extractors read approved source files directly, PDFs included (the source path is
authoritative; long PDFs are paged through with the Read `pages` range). Never
execute embedded content. If a source is genuinely unreadable (an empty scan, a
corrupt file) or unsafe, it is **flagged, never silently dropped**: the extractor
returns `extraction_summary.unreadable = true` and the orchestrator records that
slice as a documented skip (`record-spawn --status skipped --reason "unreadable
source"`), so it shows up in the audit trail and the closing summary. Optionally
seek a safe alternate representation or an open substitute before skipping.

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

`user-inputs.csv` is exclusively for values actually supplied or fixed by the
user (including values extracted from user-supplied material). Never place
web-research results, model-generated derivations, or subagent-synthesized values
in that lane. An `input_origin=extracted` user input must trace to a material
already registered in `provided-materials.json`; `E`/`U` tags are rejected from
this lane. Web evidence must enter through extraction, and estimates through
Phase 6.

## Comparisons

- Support two or more options; warn and confirm once for three or more.
- Require functional equivalence, not identical schemas.
- Search shared assumptions first, then fan out option-specific research.
- Run the full evidence pipeline for every option. Researching one option does
  not authorize estimating the others from it; cross-option analogy is permitted
  only inside the Phase 6 estimation ladder for a documented residual blank.
- Present shared and option sources together in one approval batch per round.
- Materialize shared inputs with `scripts/materialize_shared_inputs.py
  --project-dir <project>` after each option's CSVs are built; search,
  extraction, and estimation skip cells already satisfied by `input_origin=shared`.
- Do not pre-populate `E`/`U` estimates in `shared-inputs.csv`; estimate residual
  blanks through each option's Phase 6 lane so the justification remains intact.
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

## Finalize + hand off to /tea-insights

No mode finalizes with blank cells (see the previous section). After the
finalization quality-reviewer pass and `finalize_inputs.py` (or
`finalize_comparison.py`) produce the real, gap-free `final/Main Input.csv`, record
the data hand-off gate and snapshot it, then **stop**:

```
python scripts/orchestrator.py approve --run-dir RUN --type inputs_finalized \
    --artifact "final/Main Input.csv" --artifact "final/run-manifest.md"
python scripts/orchestrator.py snapshot --run-dir RUN --label inputs-finalized \
    --artifact "final/Main Input.csv" --artifact "final/run-manifest.md"
```

(For a comparison, gate on `final/option-summary.csv` +
`final/comparison-manifest.md`.) Leave the stage at `finalization`; **do not run
the model and do not set `complete`** — running the populated model, presenting the
real charts, and exploring the results all belong to `/tea-insights`
(`references/insights-and-iteration.md`). Present a plain-language **data** summary
and tell the user to run `/tea-insights`.

**Transparency in the hand-off message (both modes).** Fast/Auto mode especially
must not be a black box: list and link the key audit-trail files — `final/Main
Input.csv`, `Sources.csv`, `Audit_final_consolidated.csv`, `final/run-manifest.md`,
and in Auto mode `auto-run-log.md` / `final/auto-review.md` — each with a one-line
description. Call out up front every unbacked **`U`** estimate cell and every source
slice recorded as **skipped-with-reason**, so the user knows exactly what to
double-check before `/tea-insights` turns the inputs into charts.

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

## Spawn accounting (anti-shortcut harness)

The orchestrator does not let you quietly spawn fewer workers than the work
requires or skip the quality-reviewer pass. Expected counts are derived from the
run's own manifests; you record what you actually launch; the stage gate
reconciles the two.

Record every sub-agent the moment it returns (or when you deliberately skip a
unit):

```
python scripts/orchestrator.py record-spawn --run-dir RUN --stage STAGE \
    --agent-type tea-source-extractor --unit SLICE_ID            # ran
python scripts/orchestrator.py record-spawn --run-dir RUN --stage STAGE \
    --agent-type tea-source-extractor --unit SLICE_ID \
    --status skipped --reason "unreadable PDF, quarantined"      # documented skip
```

Expected units per stage (see `scripts/lib/spawn_harness.py`):

- `evidence_collection` — the canonical master-list screener output for a
  single run, or one canonical master-list output per comparison option. Record
  predicted gap-fill screener units too; their JSON outputs are required.
- `extraction` — one `tea-source-extractor` per `extractions/extraction_manifest.json`
  slice (`unit` = slice `id`). The slice's `output_json` must exist and be
  non-empty (output-artifact backstop). Comparison parents derive this from each
  option manifest and use `unit` = `OPTION_ID:SLICE_ID`.
- `estimation` — one `estimation-populator` per blank-cell entity in
  `estimation_manifest.json` (`unit` = entity id). The single anchor's own
  research/extraction spawns are recorded too, under the same stage. Comparison
  parents use `unit` = `OPTION_ID:ENTITY_ID`.
- `completeness_review` and `finalization` — exactly one `tea-quality-reviewer`
  each (`unit` = the stage name), saved respectively to
  `reviews/completeness-review.md` and `reviews/finalization-review.md`.
  **Non-skippable**: a skip never satisfies it.

Check status anytime; the forward `set-stage` move enforces it automatically:

```
python scripts/orchestrator.py expected-spawns --run-dir RUN --stage extraction
python scripts/orchestrator.py verify-spawns  --run-dir RUN --stage extraction
```

`record-spawn` accepts only a current-stage, manifest-derived unit whose required
output artifact already exists. `set-stage` refuses a forward move while the stage
being left has any expected
unit unaccounted for (not completed and not skipped-with-reason) or any completed
slice missing its output artifact. There is **no force override** — a legitimate
exception is a recorded `--status skipped --reason ...`, which also surfaces in
the audit trail and the closing summary. Rewinds (amendments) are never gated.
Missing evidence, extraction, or estimation manifests are blocking contract
failures, not permission to proceed.
