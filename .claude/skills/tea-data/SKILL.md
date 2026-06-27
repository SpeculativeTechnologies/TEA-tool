---
name: tea-data
description: >-
  Step 3 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data). Gathers real, citation-backed evidence
  (auto or guided), populates the approved model's inputs, then runs the model to
  produce real-data charts and results. Invoke ONLY when the user runs /tea-data
  or explicitly asks to gather data / run the model after the model is approved.
  Do not self-invoke for general TEA questions.
---

# TEA Data Acquisition + Run (/tea-data)

Skill 3 of three. You gather the real, citation-backed evidence, populate the
inputs, then **inject them into the already-approved `model.py` and run it** to
produce the final charts and results. Execution contract:
`references/interaction-and-gates.md`; pipeline authority: `workflow.md`.

Plain language; keep schemas, files, and CSVs invisible.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing.

## Gate check + startup

The CLI is the source of truth; never hand-edit state or CSVs. Run
`validate-resume`/`status`:

- If `model_approved` is **not** in `approvals.valid`, stop and tell the user to
  run `/tea-model` first (or resume it).
- If the run is already `complete`, summarize the results and the run's `plots/`.
- Otherwise resume or begin acquisition.

## 1. Choose the mode (only here)

Ask the user, in novice language, how to run the data hunt — **Guided**
(`auto_with_human_gates`, default; pauses for consequential judgments) or
**Hands-off** (`auto`; resolves downstream gates and documents assumptions) — then
set and lock it:

```
python scripts/orchestrator.py set-mode --run-dir RUN \
    --mode auto_with_human_gates|auto --lock
```

The mode is immutable once locked (changing it requires a new run) and governs
only the gate behavior in the stages below.

## 2. Gather + populate (workflow.md Phases 1–7)

Follow `workflow.md` as the execution authority, Phase 1 → 7, driving the existing
pipeline and read-only subagents (`tea-research-screener`, `tea-source-extractor`,
`tea-quality-reviewer`). `set-stage` as you advance (`evidence_collection` …
`finalization`). Materialize analyst inputs before search so fixed cells suppress
redundant research. **Benchmark cells (the reserved `BENCHMARK` entity) are
researched in these same rounds** — they are validation targets the user named at
scope time with no value, so find citation-backed literature values for them
exactly like any other cell (same screener/extractor/quality machinery, same
`Sources.csv` and audit trail). They simply are not model inputs: the model ignores
them in its formulas and surfaces them beside the computed outputs at results time. Present exactly one approval batch per research round; stage
open sources into `source-staging/` before Guided approval. Interrupt only at real
gates and consequential decisions (Guided) per
`references/interaction-and-gates.md`. No mode finalizes with blank cells; finalize
with `scripts/finalize_inputs.py` (and `scripts/finalize_comparison.py` for
comparisons), which enforces exactly one finite numeric value per cell.

## 3. Run the model + present results

After finalization produces the real, fully-populated `Main Input.csv`, run the
approved model on it and present the deliverable:

```
python "$RUN/model.py" --inputs "$RUN/Main Input.csv" \
    --outdir "$RUN/plots" --results "$RUN/model-results.json"
python scripts/export_workbook.py --run-dir "$RUN"
```

The real run writes to `plots/` and `model-results.json`; the dummy figures from
`/tea-model` stay in `plots-dummy/` (they are **not** overwritten). The workbook
step writes the viewer-friendly `<project>-model-workbook.xlsx` — a values-only
spreadsheet (no formulas) with the main input, a dashboard, the intermediate
outputs, and the charts, for people who prefer Excel to code. Present the **real**
plots, the headline metric(s), the charts, the workbook, and the key
sources/assumptions. **If the run has benchmarks, present the validation comparison
explicitly** — computed value vs. researched literature benchmark (with its source)
for each target, from `results["validation"]`. Flag any benchmark cell that ended
up **estimated rather than literature-sourced** (quality tag `E`/`U`): an estimated
benchmark is not an independent check, so call it out so the user does not read it
as one. Then `set-stage --stage complete`.

**Show where the data lives (both modes, especially Auto).** The final chat
message must not be a black box. After the results, list and **link** the key
audit-trail files, each with a one-line "what's in here", so the user can drill
into any number. Cover at least:

- `final/Main Input.csv` — the model inputs, one row per cell (value, units, tag).
- `Sources.csv` — every source with its URL and page/table reference.
- `Audit_final_consolidated.csv` — full provenance: every candidate value, which
  one won each cell, and why.
- `final/run-manifest.md` — coverage, quality distribution, and the **Unbacked
  Estimates (U)** list.
- `plots/` and `model-results.json` — the charts and the headline numbers.
- In Auto mode: `auto-run-log.md` and `final/auto-review.md` — the AI's gate
  decisions, assumptions, and estimate reasoning.

Call out, in plain language and up front, anything the user should double-check:
every **`U` (unbacked) estimate** cell, and any source slice recorded as
**skipped-with-reason** (e.g. an unreadable PDF). Get the skipped list from
`orchestrator.py verify-spawns` / the run's `subagent_jobs`; get the `U` cells
from `final/run-manifest.md`.

**Light inline model fixes.** If real data exposes a small model problem (a wrong
formula, an obviously broken chart), you may edit `runs/<project>/model.py`
directly — but that invalidates `model_approved`, so immediately re-record it and
note why in `decision-log.md`:

```
python scripts/orchestrator.py approve --run-dir RUN --type model_approved \
    --artifact model.py --artifact viz-spec.md
```

A structural change (new output, changed functional unit, a different chart set)
is **not** a light fix — send the user back to `/tea-model` to revise and
re-approve the model.

## Subagents

Read-only roles in `.claude/agents/tea-*.md` (research screener, source extractor,
quality reviewer). Subagents are read-only; you serialize all canonical writes
through the CLI and phase scripts. Apply each material's sensitivity policy; never
include confidential content in web queries. See
`references/interaction-and-gates.md` for the full subagent contract.

**No shortcuts.** Spawn the workers the work requires — one source extractor per
extraction slice, one populator per blank-cell entity, the quality-reviewer pass
before completeness review and finalization. Record each with
`orchestrator.py record-spawn` (or a documented `--status skipped --reason ...`).
The forward `set-stage` move is hard-blocked until every expected unit is
accounted for, and the quality-reviewer pass cannot be skipped — see the
"Spawn accounting" section of `references/interaction-and-gates.md`.
