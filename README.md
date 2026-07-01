# General TEA Tool

Config-driven data pipeline for techno-economic analysis input preparation.
It turns two analyst-authored documents into populated, normalized,
citation-backed model inputs, and — through the `/tea-*` orchestrator skills —
builds a runnable model from them and runs it.

The workflow is domain-agnostic. One run can describe an industrial process,
a managed compute service, a logistics workflow, or another single system, as
long as the analyst can specify the scope and data requirements clearly.

## New Users: The Orchestrator

If you have a rough idea rather than finished input documents, use the four
explicitly-invoked orchestrator skills, run **in series** (`.claude/skills/tea-scope`,
`tea-model`, `tea-data`, `tea-insights`, with a Codex shim under `.agents/` and
`.codex/`):

1. **`/tea-scope`** runs intake in plain language — a relentless, question-driven
   interview — and writes the four starting documents (`scope.md`,
   `process-flow.md`, `data-requirements.md`, `model-requirements.md`).
2. **`/tea-model`** builds a runnable `model.py` from those docs, dry-runs it on
   quick dummy values, and agrees the visualizations with you.
3. **`/tea-data`** gathers the real, citation-backed evidence and finalizes the
   gap-free model inputs.
4. **`/tea-insights`** runs the approved model on those inputs to produce the real
   charts and results, then surfaces insights and proposes new plots — each tied to
   a question about your idea — and iterates with you on plots and light model
   tweaks.

They share durable run state and an issue ledger via `scripts/orchestrator.py`;
each is hard-gated on the prior skill's approval. You approve the starting
documents, the model, and the consequential judgments; the skills handle schemas,
files, and bookkeeping. `/tea-data` offers two modes — **Guided** (pauses for
consequential decisions) and **Hands-off** (resolves downstream gates and documents
assumptions).

## What You Provide

Each run starts with two documents in a run folder:

- `scope.md`: narrative scope, boundaries, functional unit, entities, basis,
  scenarios, and validation targets.
- `data-requirements.md`: structured data contract: entities, parameters,
  applicability, rule types, quality tags, estimation policy, and reference
  values.

Setup also asks for an execution mode. **Auto with Human Gates** is the default.
**Auto** lets the AI resolve each gate without interrupting the stage flow and
records its reasoning. Both modes are numeric-only and gap-free: every parameter
resolves to one finite numeric value (`JSON`/`TEXT` parameters are rejected), and
finalization requires every schema cell to be filled in either mode — Guided
resolves each blank by an approved estimate or a supplied value, Auto estimates
it. Because Auto can only inspect open evidence, it searches specifically for
open-access full text, public datasets, government/institutional reports,
repository copies, and other publicly accessible sources.

Use these templates:

- `templates/scope.template.md`
- `templates/data-requirements.template.md`
- `templates/shared-*.template.csv` when building a comparison wrapper with
  reusable shared assumptions.

## What The Tool Produces

- `tea-schema.json`: machine-readable run contract.
- `Audit.csv`: all extracted, shared, estimated, and normalized evidence rows.
- `Sources.csv`: accepted source registry with `source_url` and `source_role`.
- `Main Input.csv`: one selected model-ready row per schema cell.
- `Reference Values.csv`: global context-free values extracted from
  `Main Input.csv`.
- `run-manifest.md`: coverage, source counts, quality distribution, shared
  inputs, gaps, and validation targets.
- `auto-review.md` in Auto mode: AI decisions, assumptions, estimates, flags,
  and technical errors.

The pipeline's hand-off is populated inputs (`Main Input.csv`); the `/tea-model`,
`/tea-data`, and `/tea-insights` skills then build, populate, and run a model on
top of them, writing figures to the run's `plots/` folder.

## Quickstart

Run commands from the repository root.

```powershell
$RUN = "runs/my-run"
New-Item -ItemType Directory -Force $RUN
Copy-Item templates/scope.template.md "$RUN/scope.md"
Copy-Item templates/data-requirements.template.md "$RUN/data-requirements.md"
```

Fill in `scope.md` and `data-requirements.md`.

Run Stage 0.1 with `prompts/stage0-schema-compile.md`. The agent reads the two
documents, asks or records open questions, writes `tea-schema.json`, and
scaffolds `conventions/*.csv`.

Validate the schema:

```powershell
python scripts/lib/schema.py "$RUN/tea-schema.json"
```

Build the working CSVs:

```powershell
python scripts/build_csvs.py --schema "$RUN/tea-schema.json" --output-dir "$RUN"
```

Then follow `workflow.md` from Phase 1 through Phase 7.

## Key Concepts

- Entity: a process unit, cost center, activity, or other scoped part of the
  system. Code and CSVs always use `entity`.
- Parameter: a data field to populate for one or more entities. Code and CSVs
  always use `parameter`.
- Functional unit: the denominator for model-ready intensities, such as
  `kg billet`, `1M tokens`, or `delivery`.
- Rule type: normalization behavior for a parameter: `MONETARY`, `INTENSITY`,
  `FRACTION`, `RATE`, `CAPEX`, `PASSTHROUGH`, `JSON`, or `TEXT`.
- Scope frame: per-entity relevance definition used to accept, hold, or reject
  extracted values.
- Reference value: a global market/background value searched without TEA
  context and stored under entity `REF`.
- Comparison shared input: reusable raw evidence mapped explicitly into one or
  more option schemas with `input_origin=shared`.

## Development

Install test dependencies if needed:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the suite:

```powershell
python -m unittest discover -s tests
```
