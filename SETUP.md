# General TEA Tool - Setup and First Run

This guide is for a first-time user running the General TEA Tool through Codex
or Claude Code. The recommended path is Codex: open the repository as a local
project and use the four TEA skills in order.

## 1. What You Need

- A local copy of this entire repository. Do not copy only the visible files:
  the hidden `.agents`, `.codex`, and `.claude` folders contain the TEA skill
  registrations and instructions.
- Codex with access to local project folders, or Claude Code.
- Python 3 available as `python` in PowerShell or your terminal.
- Git, if you are cloning the repository rather than receiving a ZIP archive.
- Internet access during `/tea-data` so the agent can find and inspect sources.

You do not need to design a spreadsheet, schema, or model before starting. A
plain-language description of the technology and the decision you want to make
is enough.

## 2. Get the Project

Clone the repository:

```powershell
git clone https://github.com/SpeculativeTechnologies/Techno-Economic-Analysis-TEA-tool.git
cd Techno-Economic-Analysis-TEA-tool
```

If you receive a ZIP archive instead, extract the whole archive and confirm
that these folders are present at the project root:

```text
.agents/
.claude/
.codex/
scripts/
templates/
```

On Windows, hidden folders may not appear in File Explorer unless **View >
Show > Hidden items** is enabled.

## 3. Install the Python Dependencies

From the repository root, run:

```powershell
python -m pip install -r requirements-dev.txt
```

This installs:

- `jsonschema` for full schema validation;
- `matplotlib` for model charts; and
- `openpyxl` for Excel workbook output.

The core data pipeline otherwise uses the Python standard library.

Optional verification:

```powershell
python -m unittest discover -s tests
```

A successful test run confirms that the local pipeline and templates are
working. It does not test internet research or your Codex/Claude account.

## 4. Open the Correct Folder

In Codex, open the cloned or extracted repository root as the project folder.
Start a new task from that folder so Codex can discover the project skills.

In Claude Code, start Claude from the repository root. The canonical skill
instructions live under `.claude/skills/`.

Do not open only `scripts/`, `templates/`, or an individual run folder as the
project. The agent needs the repository root to resolve the shared skill
instructions and helper scripts.

## 5. Verify the TEA Skills

The following four commands should be available:

```text
/tea-scope
/tea-model
/tea-data
/tea-insights
```

They are explicitly invoked and do not start automatically. If they do not
appear, check that you opened the repository root, that the hidden skill
folders were included, and that you started a new task after opening the
project.

## 6. Start Your First TEA

Begin with `/tea-scope` and a short description of the technology and decision.
Attach any useful papers, spreadsheets, pilot data, diagrams, or notes at the
start.

Example:

```text
/tea-scope I want to assess whether recycled-aluminum billet production can be
cost-competitive with primary aluminum. The main decision is whether to fund a
pilot expansion. I have attached our pilot data spreadsheet.
```

The skill will interview you one question at a time and recommend an answer to
each question. Correct its recommendation where needed. It will create and ask
you to approve the starting documents before moving on.

## 7. Run the Four Skills in Order

### Step 1: `/tea-scope`

Defines the goal, system boundary, functional unit, entities, scenarios, model
requirements, data requirements, and desired charts. It writes the approved
starting documents into a run folder under `runs/`.

### Step 2: `/tea-model`

Builds `model.py`, tests the model structure with dummy values, and agrees the
outputs and charts with you. Review the formulas, units, outputs, and chart
choices; do not judge the dummy numbers as real results.

### Step 3: `/tea-data`

Finds citation-backed evidence, populates the model inputs, and resolves every
required numeric cell. Choose one of these modes when asked:

- **Guided** - pauses for consequential source, assumption, and estimation
  decisions. Recommended for a first run.
- **Hands-off** - resolves downstream gates and records its assumptions for
  later review.

Tell the skill about trusted values early. For example:

```text
/tea-data Run Guided. Treat our contracted electricity price of $0.06/kWh as a
fixed input.
```

### Step 4: `/tea-insights`

Runs the approved model using the finalized inputs, produces the real results,
charts, and workbook, checks benchmark targets, and helps explore follow-up
questions.

Example follow-up:

```text
At what feedstock price does this stop beating the incumbent?
```

## 8. Approvals, Files, and Resuming

- Run the skills in order. Each skill checks the prior approval gate and will
  redirect you if an earlier stage is incomplete.
- Keep using the same run folder for all four stages. The skills store durable
  state and an issue ledger there.
- You can stop after an approval checkpoint and resume later. Tell the agent
  which run under `runs/` to resume if there is more than one.
- Speak in plain language. The skills are responsible for schemas, CSVs,
  filenames, commands, and bookkeeping.
- Review consequential assumptions and supplied values carefully, especially
  when they materially change the headline economics.

Typical final artifacts include:

- `Main Input.csv` - selected model-ready input values;
- `Audit.csv` - evidence, transformations, estimates, and selection history;
- `Sources.csv` - source registry and URLs;
- `model.py` and `model-results.json` - the approved model and results;
- `plots/` - model charts;
- a values-only Excel workbook; and
- `run-manifest.md` and, for hands-off runs, an automated-review record.

## 9. Troubleshooting

### The `/tea-*` skills are missing

Confirm that `.agents/`, `.codex/`, and `.claude/` exist at the repository root,
then reopen the root folder and start a new task.

### A Python command fails

Confirm that `python --version` works from the repository root, then rerun:

```powershell
python -m pip install -r requirements-dev.txt
```

### A skill says an earlier gate is incomplete

Return to the skill it names and finish or approve that stage. Do not manually
edit the orchestrator state unless you are debugging the pipeline.

### A run is using the wrong files

State the intended run folder explicitly, for example:

```text
Resume /tea-data for runs/recycled-aluminum-pilot.
```

### You need to operate the pipeline manually

Use [`workflow.md`](workflow.md). It is the authoritative phase-by-phase
operator guide; most new users should let the four skills drive it.

## Quick Reference

```text
/tea-scope    Define and approve the analysis
/tea-model    Build and approve the model
/tea-data     Gather and finalize the real inputs
/tea-insights Run the model and explore the results
```

For prompt examples and advice for each stage, see
[`README-tea-skills.md`](README-tea-skills.md).
