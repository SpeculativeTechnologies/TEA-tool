# TEA Tool

The TEA Tool is a domain-agnostic workflow for building a
techno-economic analysis (TEA) from a rough idea. It helps an analyst define
the system, build and check a model, gather citation-backed inputs, and explore
the results.

The recommended workflow uses four explicitly invoked skills in sequence:

`/tea-scope` -> `/tea-model` -> `/tea-data` -> `/tea-insights`

Each skill hands a durable run folder to the next one, with approval gates at
the important decisions. The tool manages schemas, evidence files, model
inputs, and run state while the user works in plain language.

## Documentation

- **New user:** start with [`SETUP.md`](SETUP.md) for installation, verification,
  and a first run.
- **Everyday use:** see [`README-tea-skills.md`](README-tea-skills.md) for a short
  guide to the four skills and example prompts.
- **Manual operation:** see [`workflow.md`](workflow.md) for the authoritative
  phase-by-phase data pipeline.
- **TEA structure:** see [`framework.md`](framework.md) for entities, parameters,
  normalization rules, evidence quality, and human gates.
- **Worked example:** see
  [`examples/compute-service/README.md`](examples/compute-service/README.md).

## Repository Map

- `.claude/skills/` - canonical workflow instructions shared by the supported
  agent runtimes.
- `.agents/skills/` and `.codex/skills/` - Codex skill registrations.
- `scripts/` - deterministic pipeline, orchestration, validation, and export
  commands.
- `templates/` - starting-document and schema templates.
- `prompts/` - specialist prompts used during research and data processing.
- `references/` - detailed workflow guidance loaded by the skills.
- `runs/` - local run folders and generated outputs (ignored by Git).
- `tests/` - automated tests for the pipeline.
- `docs/archive/legacy-plans/` - historical plans and the completed task board.

## Development

Install the development and model-output dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the test suite:

```powershell
python -m unittest discover -s tests
```

The core input pipeline uses the Python standard library. `jsonschema` is
recommended for full schema validation; `matplotlib` supports model charts.
