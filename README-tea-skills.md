# TEA Tool - The Four Skills

A quick guide to the four orchestrator skills that take you from a rough idea to a
runnable techno-economic analysis (TEA). They run **in series**:
`/tea-scope` -> `/tea-model` -> `/tea-data` -> `/tea-insights`. Each step is gated
on your approval of the previous step, sharing one run folder under `runs/`.

## 1. `/tea-scope` - Scoping interview

Takes you from a rough idea (plus any files, papers, or spreadsheets you supply)
to approved starting documents: a concise `scope-summary.md`, scope, process
flow, data requirements, and model requirements. It works through a
one-question-at-a-time interview (~12 questions), where every question comes with
a recommended answer you can simply confirm. The summary is the human-readable
review artifact; the other documents are mostly working artifacts for the next
TEA phases, though you can read them if you want to audit the setup. Best
prompted with a short plain-language description of your technology and the
decision you're trying to make, attaching any materials you already have up front
so they're inspected before the questions start. Don't over-prepare: answer
honestly, correct its recommendations where you know better, and let it keep
asking until the scope is genuinely unambiguous.

> Example: `/tea-scope I want to assess whether recycled-aluminum billet production is cost-competitive with primary - here's our pilot data spreadsheet.`

## 2. `/tea-model` - Build the model

Turns the approved model requirements into a runnable `model.py`, dry-runs it on
rough dummy values (no real data yet), and agrees the chart list with you before
locking the model behind an approval gate. Best prompted by just running `/tea-model` after
scoping is approved, then focusing your feedback on the model's *shape*: the
outputs, formulas, and which charts you want, not the dummy numbers. Remember the
dummy figures are a structure check only; approve the model when the logic and
visualizations look right.

> Example: `/tea-model` then: `Add a sensitivity chart for electricity price and drop the cash-flow plot.`

## 3. `/tea-data` - Gather real data

Hunts down real, citation-backed evidence for every model input, populates them
with full source and audit trails, and finalizes a gap-free input set (every cell
gets exactly one numeric value) before handing off. Best prompted by running
`/tea-data` and choosing your mode when asked: **Guided** (default; it pauses for
consequential judgments) or **Hands-off** (it resolves gates itself and documents
every assumption). The mode prompt warns once that screened public sources will
be saved into the run folder; Hands-off authorizes those noninteractive downloads
for the run, so there are no browser download/save popups or per-file prompts.
Downloaded sources are never executed. If you already have trusted numbers, say
so early so they're pinned as fixed inputs and redundant research is skipped.

> Example: `/tea-data - run it Guided; use our contracted electricity price of $0.06/kWh as a fixed input.`

## 4. `/tea-insights` - Run and explore

Runs the approved model on the finalized inputs to produce the real charts,
headline results, and benchmark validation (computed vs. literature),
then proposes new plots, each tied to a question about your idea, and iterates
open-endedly. Best prompted by running `/tea-insights` and then asking business
questions in plain language ("what would make this break even?", "which input
matters most?") rather than requesting specific chart types. It's re-runnable, so
come back anytime to explore further with new plots or light model tweaks.

> Example: `/tea-insights` then: `At what feedstock price does this stop beating the incumbent?`

## Tips that apply to all four

- Invoke them explicitly (`/tea-scope`, etc.); they never trigger themselves.
- Talk in plain language; the skills handle all schemas, CSVs, and state files for you.
- Each skill checks the previous gate and will redirect you if you're out of order, so you can't break anything by invoking the wrong one.
