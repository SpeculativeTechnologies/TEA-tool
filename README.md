# General TEA Tool

Config-driven data pipeline for techno-economic analysis input preparation.
It turns two analyst-authored documents into populated, normalized,
citation-backed model inputs. It does not build or run the analyst's model.

The workflow is domain-agnostic. One run can describe an industrial process,
a managed compute service, a logistics workflow, or another single system, as
long as the analyst can specify the scope and data requirements clearly.

## What You Provide

Each run starts with two documents in a run folder:

- `scope.md`: narrative scope, boundaries, functional unit, entities, basis,
  scenarios, and validation targets.
- `data-requirements.md`: structured data contract: entities, parameters,
  applicability, rule types, quality tags, estimation policy, and reference
  values.

Use these templates:

- `templates/scope.template.md`
- `templates/data-requirements.template.md`
- `templates/pinned-inputs.template.csv` when carrying locked values from a
  prior run.

## What The Tool Produces

- `tea-schema.json`: machine-readable run contract.
- `Audit.csv`: all extracted, estimated, pinned, and normalized evidence rows.
- `Sources.csv`: accepted source registry with `source_url` and `source_role`.
- `Main Input.csv`: one selected model-ready row per schema cell.
- `Reference Values.csv`: global context-free values extracted from
  `Main Input.csv`.
- `run-manifest.md`: coverage, source counts, quality distribution, pinned
  cells, gaps, and validation targets.

The final stop is populated inputs. Model execution and back-casting stay
outside this tool.

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
- Pinned input: an analyst-supplied cell treated as authoritative, normalized
  like any other row, skipped by search/extraction/estimation, and locked in
  consolidation.

## Development

Install test dependencies if needed:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the suite:

```powershell
python -m unittest discover -s tests
```
