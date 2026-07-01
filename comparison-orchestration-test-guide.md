# Comparison TEA Orchestration Test Guide

This guide is for an LLM orchestrating a cheap user-style smoke test of the
General TEA Tool's comparison workflow. The user should feel like the analyst,
not the researcher: ask them only for source/gate approvals and any genuinely
ambiguous judgment calls.

The most important behavior to test is the orchestration loop. At each workflow
stage, briefly tell the user what happened, what you found, what decisions are
available, and what you recommend. Keep these updates concise but complete
enough that the user can approve, redirect, or inspect without doing their own
research.

## Test Idea

Compare two lighting options for the same service:

- Option A: 60 W legacy incandescent A19 bulb.
- Option B: 60 W-equivalent LED A19 bulb.
- Functional unit: `1,000 lamp-hours at roughly 800 lumens`.
- Geography and basis: United States, USD, base year 2025, CPI.
- Scope: input-preparation only. The downstream model can later compute
  electricity cost and replacement cost per functional unit.

Why this is a good comparison test:

- Two options have the same schema and shared functional unit.
- One shared reference value, residential electricity price, should be
  materialized into both option runs with `input_origin=shared`.
- Option-specific evidence can come from one product/spec source per bulb type.
- The test needs only three or four LLM searches and very small source files.

## Cheap Search Plan

Keep the source hunt deliberately small.

1. Shared source search:
   `EIA average residential electricity price United States 2025 USD per kWh`
2. Incandescent source search:
   `60 watt A19 incandescent bulb wattage lifetime lumens source`
3. LED source search:
   `60 watt equivalent A19 LED bulb wattage lifetime lumens source`
4. Optional product-price search only if the first bulb sources lack prices:
   `60W A19 incandescent bulb price 4 pack` and
   `60W equivalent A19 LED bulb price 4 pack`

Prefer official or stable sources first: EIA, ENERGY STAR, DOE/Energy Saver,
manufacturer product pages, or retailer pages with visible specs. Avoid
paywalled sources and sources that require the user to browse manually.

## Interaction Contract

Use this pattern throughout the run:

```text
Stage: <workflow phase/stage name>
What I did: <1-3 bullets>
What I found: <key values, sources, files, gaps, or script results>
Decision needed: <one clear decision, or "none">
My recommendation: <default action and why>
Next if approved: <exact next stage>
```

Tie every update to the exact numbered label from `workflow.md`, such as
`workflow.md Phase 1.2 - Screen And Download Gate`. Include one sentence on the
stage goal in plain language, as if the user is new to the tool.

Do not jump across numbered stages. At the end of every labeled, numbered stage
in `workflow.md`, stop and send the contract block above. This applies even when
the stage is a no-op, has no substantive analyst decision, or the recommended
action is obvious. The user must explicitly approve before the orchestrator runs
commands or makes file edits for the next numbered stage.

Use `Decision needed: none; approval requested to continue` when there is no
substantive choice but the checkpoint is still required. Use
`Next if approved:` to name exactly one next numbered stage. Do not combine
multiple future stages in one "next" line.

Pause especially carefully when the workflow has a human gate, when a source is
weak, when a schema question is blocking, when there are multiple plausible
policy choices, or when the recommended action is to skip a phase. A skipped
phase still gets its own checkpoint and approval request.

For any stage that takes more than a few minutes, give a short progress update
before the stage is complete:

```text
Progress: I am still in <stage>. So far I have found <brief finding>. The main
decision I expect to bring you is <likely decision/none>.
```

Keep the user out of raw research. When asking for a decision, present the
source title, publisher, URL, extracted value candidates, and the recommended
choice. Do not ask the user to find facts manually.

## Required Numbered Checkpoints

Use this map when walking `workflow.md`. Each checkpoint needs a short summary,
the stage goal, what was found, a recommendation, and explicit approval before
continuing.

- `workflow.md Phase 0.1 - Compile Schema`: prove the option run contracts are
  valid and unambiguous before any data gathering.
- `workflow.md Phase 0.2 - Build Working CSVs`: prove each option has the
  working tables and source folders required by the deterministic pipeline.
- `workflow.md Phase 1.1 - Search`: produce candidate source JSON only; do not
  download or register anything yet.
- `workflow.md Phase 1.2 - Screen And Download Gate`: ask the user to approve
  sources before saving files; report source quality, coverage, and weaknesses.
- `workflow.md Phase 1.3 - Normalize Filenames`: dry-run file matching first,
  summarize matches, and ask approval before applying any rename or copy.
- `workflow.md Phase 1.4 - Register Sources`: register only approved local
  source files in `Sources.csv`.
- `workflow.md Phase 2.1 - Search Per Entity`: run only if important cells are
  uncovered; if skipped, say why and request approval to continue.
- `workflow.md Phase 2.2 - Screen And Download Gate`: gate any gap-fill sources
  the same way as Phase 1.2.
- `workflow.md Phase 2.3 - Normalize Filenames`: dry-run gap-fill source
  matching and ask approval before applying.
- `workflow.md Phase 2.4 - Register Sources`: register approved gap-fill source
  files.
- `workflow.md Phase 3.1 - Build Manifest And Run Batches`: build extraction
  manifests and produce extractor JSON, but do not ingest yet without the stage
  checkpoint.
- `workflow.md Phase 3.2 - Resolve Scope-Relevance Holds`: summarize any holds
  and ask for decisions; if there are no holds, still checkpoint.
- `workflow.md Phase 3.3 - Ingest Complete Set`: confirm all intended extractor
  outputs are ingested or intentionally omitted.
- `workflow.md Phase 4.1 - Normalize`: run normalization and summarize clear
  rows, flags, and failed rows.
- `workflow.md Phase 4.2 - Resolve Normalization Flags`: ask for approval of
  each reject, agent calculation, or other handling choice.
- `workflow.md Phase 4.3 - Resolve Cross-Source Disagreements`: summarize
  disagreements or explicitly report none.
- `workflow.md Phase 4.4 - Consolidate To Main Input`: write selected rows to
  `Main Input.csv` and report filled cells and gaps.
- `workflow.md Phase 5 - Completeness Review`: ask whether to estimate, search
  again, or accept gaps. If recommending a skip of Phase 6, do not finalize yet;
  wait for approval.
- `workflow.md Phase 6.1 - Estimate Remaining Blanks`: run only after explicit
  approval from Phase 5.
- `workflow.md Phase 6.2 - Resolve Held Estimates`: ask for approval, rejection,
  or override of held estimates.
- `workflow.md Phase 6.3 - Normalize And Re-Consolidate Estimate Rows`: rerun
  normalization/consolidation for estimates and report updated coverage.
- `workflow.md Phase 7.1 - Finalize Inputs`: finalize each option run and report
  the final option artifacts.
- `workflow.md Phase 7.2 - Finalize Comparison Project`: validate the wrapper
  and emit comparison-level artifacts. This is the only stage that may end the
  run.

## Project Layout

Create this comparison project:

```text
runs/lighting-comparison-test/
  comparison-frame.json
  shared-sources.csv
  shared-inputs.csv
  shared-input-mappings.csv
  options/
    incandescent/
      scope.md
      data-requirements.md
      tea-schema.json
      ...
    led/
      scope.md
      data-requirements.md
      tea-schema.json
      ...
```

Use the normal workflow for each option run, then the comparison wrapper:

```powershell
$COMPARISON = "runs/lighting-comparison-test"
$INC = "$COMPARISON/options/incandescent"
$LED = "$COMPARISON/options/led"
```

## Minimal Schema Shape

The Stage 0 compiler may write the full JSON, but these are the intended cells.

Entities:

- `lamp`: the bulb or lamp hardware.
- `electricity_use`: electricity consumed while providing light.
- `REF`: global reference values.

Parameters:

- `rated_wattage`: `PASSTHROUGH`, units `W`, applies to `electricity_use`,
  first class.
- `lamp_lifetime`: `PASSTHROUGH`, units `h/lamp`, applies to `lamp`, first
  class.
- `bulb_price`: `MONETARY`, canonical unit `USD/lamp`, applies to `lamp`, first
  class. If price sourcing gets annoying, keep the cell and let estimation or a
  documented gap exercise the later workflow.
- `lumens`: `PASSTHROUGH`, units `lm`, applies to `lamp`, useful for
  scope fit.
- `electricity_price`: `MONETARY`, canonical unit `USD/kWh`, `context_free:
  true`, `reference_value: true`, applies only to `REF`.
- `notes`: `TEXT`, optional.

Shared input target:

- `shared-us-residential-electricity-price` maps to
  `REF,electricity_price` in both options.

## Scope Draft For Both Options

Write nearly identical `scope.md` files, changing only the option name and
technology description.

```markdown
# Lighting Service TEA Scope - <Option Display Name>

## Goal and framing

This run prepares model inputs for one option in a comparison of household
lighting technologies. The comparison asks for the input data needed to estimate
cost per 1,000 lamp-hours at roughly 800 lumens.

## System boundary

In scope:

- One A19 bulb providing roughly 60 W-incandescent-equivalent light output.
- Electricity consumed by the bulb during operation.
- Bulb replacement based on rated lifetime.
- Bulb purchase price if a simple public source is available.

Out of scope:

- Fixture cost, installation labor, taxes, shipping, dimmer compatibility,
  disposal, and room-level lighting design.
- Manufacturing emissions or lifecycle assessment.

## Functional unit

1,000 lamp-hours at roughly 800 lumens.

## Entity decomposition

| Entity | Name | Output | Description |
|---|---|---|---|
| lamp | Lamp hardware | Bulb service life | The bulb itself, including purchase price and rated lifetime. |
| electricity_use | Electricity use | Light service | Electricity consumed to provide the functional unit. |

## Basis assumptions

| Item | Value |
|---|---|
| Currency | USD |
| Base year | 2025 |
| Inflation index | CPI |
| Geography | United States |
| Quality tags | A, B, C, D, E |

## Option-specific scope

<For incandescent: Legacy 60 W A19 incandescent bulb, roughly 800 lumens.>
<For LED: 60 W-equivalent A19 LED bulb, roughly 800 lumens.>

## Headline metrics

The downstream model is expected to calculate electricity cost, replacement
cost, and total simple operating plus bulb cost per 1,000 lamp-hours. This
workflow stops before model execution.
```

## Data Requirements Draft For Both Options

```markdown
# Lighting Service TEA Data Requirements - <Option Display Name>

## Entities

| ID | Display name | Output | Scope frame | Known out of scope | Estimation policy |
|---|---|---|---|---|---|
| lamp | Lamp hardware | Bulb service life | A19 bulb providing roughly 60 W-equivalent light output. | Fixtures, installation, shipping, taxes, disposal. | first_principles_only |
| electricity_use | Electricity use | Light service | Electricity consumed by the bulb while operating. | Household wiring losses, dimming behavior, room lighting design. | first_principles_only |

## Parameter catalog

| Parameter ID | Label | Rule type | Applies to | First class | Notes |
|---|---|---|---|---|---|
| rated_wattage | Rated wattage | PASSTHROUGH | electricity_use | true | Bulb rated wattage in W. |
| lamp_lifetime | Lamp lifetime | PASSTHROUGH | lamp | true | Rated operating lifetime in h/lamp. |
| bulb_price | Bulb price | MONETARY | lamp | true | Simple public purchase price in USD/lamp when available. |
| lumens | Light output | PASSTHROUGH | lamp | false | Rated light output in lumens for scope fit. |
| notes | Notes | TEXT | all | false | Free-text support notes. |

## Reference values

These values are searched context-free and carried under `REF`.

| Parameter ID | Label | Rule type | Canonical unit | Market basis |
|---|---|---|---|---|
| electricity_price | Residential electricity price | MONETARY | USD/kWh | US residential average retail electricity price |

## Applicability

Reference values apply only to `REF`. `rated_wattage` applies to
`electricity_use`. `lamp_lifetime`, `bulb_price`, and `lumens` apply to `lamp`.

## Estimation

Prefer direct product/spec data. If bulb price cannot be found cheaply, leave it
as a documented gap or estimate from a clearly cited retail source.

## Quality tags

Use A, B, C, D, and E. E is reserved for estimates.

## Conventions needed

- inflation_index:CPI
- currency_rates
```

## Orchestration Flow

This checklist describes the overall route, but it does not override the
required numbered checkpoints above. Whenever a checklist item spans more than
one numbered stage from `workflow.md`, expand it and stop after each numbered
stage for summary and approval.

1. Read `README.md`, `workflow.md`, and the three comparison scripts:
   `validate_comparison_project.py`, `materialize_shared_inputs.py`, and
   `finalize_comparison.py`.
2. Create the comparison folder and the two option folders.
3. Write `scope.md` and `data-requirements.md` for both options from the drafts
   above.
4. Run Stage 0 schema compilation for each option using
   `prompts/stage0-schema-compile.md`.
5. Validate both schemas:

```powershell
python scripts/lib/schema.py "$INC/tea-schema.json"
python scripts/lib/schema.py "$LED/tea-schema.json"
```

6. Build working CSVs for both options:

```powershell
python scripts/build_csvs.py --schema "$INC/tea-schema.json" --output-dir "$INC"
python scripts/build_csvs.py --schema "$LED/tea-schema.json" --output-dir "$LED"
```

7. Do the shared electricity-price search first. Fill:
   `shared-sources.csv`, `shared-inputs.csv`, and
   `shared-input-mappings.csv`.
8. Write `comparison-frame.json`, pointing to both option folders.
9. Validate and materialize shared inputs:

```powershell
python scripts/validate_comparison_project.py --project-dir "$COMPARISON"
python scripts/materialize_shared_inputs.py --project-dir "$COMPARISON" --dry-run
python scripts/materialize_shared_inputs.py --project-dir "$COMPARISON"
```

10. Run master-list search separately for each option, but tell the search LLM
    that `REF,electricity_price` is already shared and should not be searched
    again unless validation fails.
11. Download or save only the approved small source pages/PDFs into each
    option's `master list sources/` folder.
12. Continue the normal workflow one numbered stage at a time for each option:
    Phase 3.1, Phase 3.2, Phase 3.3, Phase 4.1, Phase 4.2, Phase 4.3,
    Phase 4.4, Phase 5, optional Phase 6.1-6.3, and Phase 7.1. Stop after each
    numbered stage and request approval before continuing.
13. Finalize the comparison as `workflow.md` Phase 7.2 only after Phase 7.1 has
    been summarized and approved:

```powershell
python scripts/validate_comparison_project.py --project-dir "$COMPARISON"
python scripts/finalize_comparison.py --project-dir "$COMPARISON"
```

## Stage Briefing Script

Use these briefings as the backbone of the orchestration. Adapt numbers and
details to what actually happens. These examples are not permission to batch
stages together; the required numbered checkpoints remain authoritative.

### Start: Proposed Test

Before creating files, send:

```text
I propose a small comparison TEA: legacy 60 W incandescent A19 vs 60 W-equivalent
LED A19 for 1,000 lamp-hours. I chose it because the shared assumption is simple
and the option-specific sources should be one product/spec page each.

Decision needed: approve this test topic, or tell me a different simple
comparison.
My recommendation: approve it; it should exercise shared inputs without turning
into a research project.
```

### Phase 0.1: Scope And Schema Compilation

After drafting `scope.md`, `data-requirements.md`, and compiling each
`tea-schema.json`, send:

```text
Stage: Phase 0.1 schema setup
What I did: created the two option scopes and data requirements; compiled both
schemas; checked that basis and functional unit match the comparison frame.
What I found: <schema paths>; <cell counts>; shared target is REF/electricity_price
in both options; open questions are <none/list>.
Decision needed: <"none; approval requested to continue" if validation passes;
otherwise name each blocking schema question>.
My recommendation: <continue / answer questions with proposed defaults>.
Next if approved: build working CSVs and materialize the shared-input wrapper.
```

If Stage 0 produces open questions, group them into "blocking" and "nonblocking"
instead of pasting a long file.

### Phase 0.2: Working CSVs

After running `build_csvs.py` for both options:

```text
Stage: Phase 0.2 working CSVs
What I did: built Audit, Sources, Main Input, and source folders for both option
runs.
What I found: incandescent has <n> skeleton cells; LED has <n> skeleton cells;
both include the shared reference target.
Decision needed: none; approval requested to continue.
My recommendation: continue to shared electricity-price sourcing.
Next if approved: find one shared source and ask you to approve it.
```

### Comparison Wrapper: Shared Source Search And Materialization

After the EIA/shared source search, before writing or materializing shared
inputs:

```text
Stage: comparison shared input source gate
What I did: searched for a context-free US residential electricity price source.
What I found: <source title>, <publisher>, <year>, <URL>; candidate value
<value> <units>; basis notes <basis/page/table>.
Decision needed: approve this as the shared electricity price for both options,
or request one more search.
My recommendation: approve <source_key> because <short reason>.
Next if approved: write shared-sources.csv, shared-inputs.csv, mappings, then
dry-run materialization.
```

After validation and materialization:

```text
Stage: comparison shared input materialization
What I did: validated the comparison wrapper; dry-ran materialization; wrote the
shared REF/electricity_price row into both option runs.
What I found: validator result <pass/fail>; materialized <n> shared rows and
<n> source references per option.
Decision needed: none; approval requested to continue unless validation failed.
My recommendation: continue to option-specific master-list searches.
Next if approved: find one compact source for the incandescent option and one
for the LED option.
```

### Phase 1: Master-List Search

After candidate searches for each option, before downloading/registering:

```text
Stage: Phase 1 source screening
What I did: searched for option-specific sources and filtered out sources that
do not cover rated wattage, lifetime, lumens, or price.
What I found:
- Incandescent: <candidate source>, covers <fields>, likely quality <tag>, URL <url>.
- LED: <candidate source>, covers <fields>, likely quality <tag>, URL <url>.
- Shared electricity price is already covered, so I did not re-search it.
Decision needed: approve these sources, request one more search for either
option, or allow price to remain a later gap/estimate.
My recommendation: approve <source keys>; <price recommendation>.
Next if approved: save/download the approved sources, normalize filenames, and
register them.
```

After registering:

```text
Stage: Phase 1 registration
What I did: saved approved source files, normalized filenames, and registered
source rows in each option's Sources.csv.
What I found: <n> source(s) registered for incandescent; <n> for LED; any failed
filename/source matches were <none/list>.
Decision needed: none; approval requested to continue unless a source-file match
looks wrong.
My recommendation: continue to extraction.
Next if approved: build extraction manifests and extract values.
```

### Phase 2: Gap-Fill Search

Only run this if Phase 1 leaves important search-targetable cells uncovered. Report:

```text
Stage: Phase 2 gap-fill decision
What I did: checked coverage after master-list screening.
What I found: remaining gaps are <list by option and cell>.
Decision needed: run one more targeted search, estimate later, or accept the
gap for this smoke test.
My recommendation: <usually one more search for rated_wattage/lifetime; estimate
or skip weak price data>.
Next if approved: <gap-fill search / extraction / estimation>.
```

### Phase 3: Extraction

After extraction and ingestion:

```text
Stage: Phase 3 extraction
What I did: extracted values from the approved sources and ingested them into
Audit.csv for both options.
What I found:
- Incandescent: <rated_wattage>, <lamp_lifetime>, <lumens>, <bulb_price/gap>.
- LED: <rated_wattage>, <lamp_lifetime>, <lumens>, <bulb_price/gap>.
- Scope holds: <none/list>.
Decision needed: resolve any scope holds or approve continuing.
My recommendation: <accept/reject/re-extract recommendations for each hold>.
Next if approved: normalize extracted rows.
```

If there are held questions, show only the row id/cell, source, why it is held,
and recommended verdict.

### Phase 4: Normalize And Consolidate

After normalization, flag sweeps, disagreement sweeps, and consolidation:

```text
Stage: Phase 4 normalization and consolidation
What I did: normalized extracted/shared values, checked flags, checked
cross-source disagreements, and consolidated to Main Input.csv.
What I found: <filled/total cells per option>; normalization flags <none/list>;
value disagreements <none/list>; shared electricity price selected in both
options <yes/no>.
Decision needed: resolve flags/disagreements if present.
My recommendation: <specific action for each flag or disagreement; otherwise
continue>.
Next if approved: review completeness and decide whether to estimate or accept
gaps.
```

### Phase 5: Completeness Review

After reviewing `Main Input.csv`:

```text
Stage: Phase 5 completeness review
What I did: reviewed final populated cells before estimation.
What I found:
- Incandescent filled cells: <summary>.
- LED filled cells: <summary>.
- Residual gaps: <list>.
Decision needed: estimate remaining blanks, run another gap-fill search, or
accept documented gaps for this smoke test.
My recommendation: <recommend the cheapest defensible route>.
Next if approved: <estimation / finalization>.
```

### Phase 6: Estimation

Only run estimation if needed. After estimator output:

```text
Stage: Phase 6 estimation
What I did: estimated remaining cells and registered cited estimate sources.
What I found: <estimated cells and values>; confidence <high/medium/low>;
held estimates <none/list>.
Decision needed: approve/reject held estimates or override with a user value.
My recommendation: <specific verdict per estimate>.
Next if approved: normalize estimate rows and reconsolidate.
```

### Phase 7.1: Option Finalization

After `finalize_inputs.py` for both options:

```text
Stage: Phase 7.1 option finalization
What I did: finalized model-ready inputs for both option runs.
What I found: final files at <paths>; each run has <filled/total> cells; shared
input count <n>; residual gaps <list/none>.
Decision needed: none; approval requested to continue unless you want to inspect
a specific file before the comparison wrapper finalization.
My recommendation: finalize the comparison manifest.
Next if approved: run comparison validation and finalization.
```

### Phase 7.2: Comparison Finalization

After `finalize_comparison.py`:

```text
Stage: Phase 7.2 comparison finalization
What I did: validated the wrapper and emitted comparison-level artifacts.
What I found: shared assumptions at <path>; option summary at <path>; manifest
at <path>; headline outcome is <coverage/gaps only, not model results>.
Decision needed: choose whether to inspect, rerun with richer sources, or stop.
My recommendation: stop if the purpose is testing workflow mechanics; rerun only
if the comparison implementation surfaced a bug or surprising UX issue.
```

## Comparison Wrapper Starter Artifacts

Use this `comparison-frame.json` shape after both option schemas exist:

```json
{
  "comparison_id": "lighting-led-vs-incandescent",
  "display_name": "LED vs Incandescent Lighting Service",
  "functional_unit": {
    "name": "1,000 lamp-hours at roughly 800 lumens",
    "symbol": "1000 lamp-h"
  },
  "basis": {
    "currency": "USD",
    "base_year": 2025,
    "inflation_index": "CPI",
    "geography": "US"
  },
  "headline_metrics": [
    "electricity cost per 1,000 lamp-hours",
    "replacement cost per 1,000 lamp-hours"
  ],
  "options": [
    {
      "option_id": "incandescent",
      "display_name": "Legacy Incandescent A19",
      "run_dir": "options/incandescent",
      "schema_path": "options/incandescent/tea-schema.json"
    },
    {
      "option_id": "led",
      "display_name": "LED A19",
      "run_dir": "options/led",
      "schema_path": "options/led/tea-schema.json"
    }
  ]
}
```

Use these CSV skeletons, replacing the placeholder source fields after the EIA
search:

```csv
source_key,authors,title,year,publisher_or_journal,source_url,doi,access_date,page_or_table_reference,source_role,notes
eia-residential-electricity-price,EIA,<title>,2025,U.S. Energy Information Administration,<url>,,<access-date>,<table/series>,extraction,Shared US residential electricity price
```

```csv
shared_input_id,raw_value,raw_units,raw_basis_scale,raw_basis_scale_units,raw_basis_year,source_key,page_ref,quality_tag,notes
shared-us-residential-electricity-price,<value>,USD/kWh,,,2025,eia-residential-electricity-price,<table/series>,B,Context-free shared reference for both lighting options
```

```csv
shared_input_id,option_id,entity,parameter,notes
shared-us-residential-electricity-price,incandescent,REF,electricity_price,Apply shared US residential electricity price to incandescent option
shared-us-residential-electricity-price,led,REF,electricity_price,Apply shared US residential electricity price to LED option
```

## Success Criteria

The test is successful if:

- `validate_comparison_project.py` passes before and after materialization.
- Both option `Main Input.csv` files contain a shared `REF,electricity_price`
  row with `input_origin=shared`.
- Each option has at least `rated_wattage` populated from an option-specific
  source.
- `finalize_inputs.py` succeeds for both options, even if `bulb_price` remains
  a documented gap.
- `finalize_comparison.py` emits:
  - `final/shared-assumptions.csv`
  - `final/option-summary.csv`
  - `final/comparison-manifest.md`

## Keep It Cheap

Stop after the first credible shared source and first credible option-specific
source for each option. This is a workflow test, not a defensible lighting TEA.
Prefer exercising the comparison implementation over perfecting the economics.
