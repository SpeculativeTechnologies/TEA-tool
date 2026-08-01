---
name: tea-data
description: >-
  Step 3 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope → /tea-model → /tea-data → /tea-insights). Gathers real,
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
  `complete`), data acquisition is **done** — offer two ways to continue: **start
  a new thread/task and invoke `/tea-insights` there**, or type **`/clear`** and
  continue with `/tea-insights` to run the model and explore the results.
  Emphasize that clearing or using a new thread keeps the tool performant.
- Otherwise resume or begin acquisition.

When acquisition will begin or resume (the last branch above), use the **first
user-facing response after the gate check** to briefly explain the data-quality
labels. Use any project-specific definitions in the approved data requirements;
otherwise use this default plain-language rubric:

- **A** — strongest: peer-reviewed or audited primary measurements that fit the
  relevant scale and boundary.
- **B** — authoritative institutional evidence, such as government, standards,
  research-institute, or major industry-association reports and datasets.
- **C** — reputable secondary evidence or a published modeled value.
- **D** — a weaker but still traceable engineering fallback.
- **E** — an estimate derived from cited evidence rather than a value reported
  directly for the exact model input.
- **U** — an unbacked estimate used only when no defensible source-backed value
  can be built; flag it for the user to verify.

Tell the user that the label describes the value's evidence basis, not a
guarantee of accuracy; the workflow prefers A/B evidence and gives extra
scrutiny to D/E/U values. Keep this orientation concise. If no mode is locked,
put it in the same response as the Guided vs. Hands-off question; on resume,
put it before the brief resume update instead.

## 1. Choose the mode (only here)

Ask the user, in novice language, how to run the data hunt — **Guided**
(`auto_with_human_gates`, default; pauses for consequential judgments) or
**Hands-off** (`auto`; resolves downstream gates and documents assumptions) — then
set and lock it:

In the same mode-choice message, give this one-time download notice in plain
language: the data hunt saves copies of screened public research sources inside
the run folder so their evidence can be extracted and audited; downloads happen
noninteractively, no browser download/save popups are used, and downloaded files
are treated as inert evidence and never executed. Explain that choosing
Hands-off authorizes these ordinary public-source downloads for the rest of the
run, without a confirmation per file. Do not repeat the notice at every source.

```
python scripts/orchestrator.py set-mode --run-dir RUN \
    --mode auto_with_human_gates|auto --lock
```

The mode is immutable once locked (changing it requires a new run) and governs
only the gate behavior in the stages below.

For source retrieval in either mode, use `scripts/download_sources.py` or an
equivalent noninteractive HTTP fetch into the run folder. Never click a browser
download control, invoke a GUI Save As flow, or ask the user to operate a
download popup. A runtime-enforced network permission may still need to be
honored, but it is not a source-by-source workflow gate. If direct retrieval
fails, record the failure and seek an open alternate representation; do not fall
back to an interactive browser download.

**Evidence depth is not a mode or a user choice.** Guided vs. Hands-off changes
who resolves gates, never whether the evidence stages run. Do not ask how much
to research, offer an estimation-led/fast path, or shorten research because of
runtime, token, or subagent cost. Search, screen, download, and extract real
sources first; create estimates only in Phase 6 for cells that remain blank
after the recorded evidence pipeline and completeness review.

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

Keep worker roles separated. A research screener returns source candidates only;
an extractor reads an approved source and returns extracted evidence only; an
estimation populator runs only from `estimation_manifest.json`. Never ask one
worker to search and populate every cell, never turn a worker's synthesized
values into `user-inputs.csv`, and never treat model-generated values as analyst
inputs. `A`–`D` tags require real extracted evidence; derived values are `E`
(backed) or `U` (unbacked) and must pass through Phase 6.

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
**data** summary and **stop, explicitly telling the user: "Start a new thread/task
and invoke `/tea-insights` there, or type `/clear` and continue with
`/tea-insights`"** to run the model and explore the results. Emphasize that
clearing or using a new thread keeps the tool performant.

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

Record a spawn only while its stage is current, only for a manifest-derived
unit, and only after its required output artifact exists. Do not reconstruct or
backfill spawn accounting after advancing or finalizing.
