---
name: tea-data
description: >-
  Step 3 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data -> /tea-insights). Gathers real,
  citation-backed evidence (auto or guided), populates the approved model's
  inputs, and finalizes the gap-free input set, then hands off to /tea-insights to
  run the model. Invoke ONLY when the user runs /tea-data or explicitly asks to
  gather data / finalize inputs after the model is approved. Do not self-invoke for
  general TEA questions.
---

# TEA Data Acquisition (/tea-data)

Skill 3 of four. You gather the real, citation-backed evidence and populate the
inputs, then **finalize the gap-free input set and hand off to `/tea-insights`**,
which runs the already-approved `model.py` to produce the charts and results.
Execution contract: `references/interaction-and-gates.md`; pipeline authority:
`workflow.md`.

Plain language; keep schemas, files, and CSVs invisible.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing.

## Gate check + startup

The CLI is the source of truth; never hand-edit state or CSVs. Run
`validate-resume`/`status`:

- If `model_approved` is **not** in `approvals.valid`, stop and tell the user to
  run `/tea-model` first (or resume it).
- If `inputs_finalized` is already in `approvals.valid` (or the run is
  `complete`), data acquisition is **done** — point the user to `/tea-insights` to
  run the model and explore the results.
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

## 3. Finalize + hand off to /tea-insights

Finalization (`workflow.md` Phase 7) runs the mandatory `tea-quality-reviewer`
pass and `scripts/finalize_inputs.py` (and `scripts/finalize_comparison.py` for
comparisons), producing the real, gap-free `final/Main Input.csv`. Once that
succeeds, record the data hand-off gate and snapshot it:

```
python scripts/orchestrator.py approve --run-dir RUN --type inputs_finalized \
    --artifact "final/Main Input.csv" --artifact "final/run-manifest.md"
python scripts/orchestrator.py snapshot --run-dir RUN --label inputs-finalized \
    --artifact "final/Main Input.csv" --artifact "final/run-manifest.md"
```

For a comparison project, gate on the comparison outputs instead
(`--artifact "final/option-summary.csv" --artifact "final/comparison-manifest.md"`).

Leave the stage at `finalization` — **do not run the model and do not set
`complete`** (those belong to `/tea-insights`). Then present a plain-language
**data** summary and **stop, telling the user to run `/tea-insights`** to run the
model and explore the results.

**Show where the data lives (both modes, especially Auto).** The hand-off message
must not be a black box. List and **link** the key audit-trail files, each with a
one-line "what's in here", so the user can drill into any number. Cover at least:

- `final/Main Input.csv` — the model inputs, one row per cell (value, units, tag).
- `Sources.csv` — every source with its URL and page/table reference.
- `Audit_final_consolidated.csv` — full provenance: every candidate value, which
  one won each cell, and why.
- `final/run-manifest.md` — coverage, quality distribution, and the **Unbacked
  Estimates (U)** list.
- In Auto mode: `auto-run-log.md` and `final/auto-review.md` — the AI's gate
  decisions, assumptions, and estimate reasoning.

Call out, in plain language and up front, anything the user should double-check
before `/tea-insights` turns these inputs into charts: every **`U` (unbacked)
estimate** cell, and any source slice recorded as **skipped-with-reason** (e.g. an
unreadable PDF). Get the skipped list from `orchestrator.py verify-spawns` / the
run's `subagent_jobs`; get the `U` cells from `final/run-manifest.md`.

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
