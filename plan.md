# General TEA Tool — Design & Build Plan

A reusable, config-driven version of the Vicky TEA data-research-and-extraction
workflow that works for **any** techno-economic analysis — industrial or not —
starting from two human-authored input documents and ending with a fully
populated, model-ready input set that the analyst feeds into their own
pre-built model.

> **Status:** design frozen after a `/grill-me` session (16 decisions, logged
> in §1). Next step is implementation by other agents — see the task breakdown
> in §11 / [`TASKS.md`](TASKS.md).
>
> **Source material:** this generalizes the Ti-6Al-4V workflow in
> `../Vicky TEA/` (its `plan.md`, `workflow.md`, `TEA Framework.md`, `prompts/`,
> `scripts/`, `conventions/`, and the `Run 2/` artifacts). That folder is the
> **reference**, not the build target — we are doing a fresh rewrite (§1, D16).

---

## 0. What this tool is (and is not)

**Is:** the data pipeline that turns a *well-specified TEA scope + data
requirements* into a populated, normalized, consolidated, citation-backed
`Main Input` (plus reference values), ready to drop into a model the analyst
already built. It covers: schema compile → master-list search → gap-fill search
→ extraction → normalization → consolidation → estimation gap-fill, with the
human-in-the-loop review gates that keep wrong/contaminating data out.

**Is not:**
- A model builder. The analyst builds and exercises their model on **dummy
  data before** running this workflow (D1, D11). The tool's terminal deliverable
  is the populated inputs; running the model and any back-cast is the analyst's
  job, outside the tool.
- Multi-system in one run. One run = one system/configuration (D14). Comparison
  TEAs are supported via a **comparison wrapper with shared inputs** (§7), not
  a route dimension inside `tea-schema.json`.
- Industrial-only. Every industrial assumption (per-kg-output, yield/mass
  balance, CapEx/CEPCI, process routes, stoichiometry) is now optional/declared,
  not hardcoded.

---

## 1. Decision log (from the grill session)

| # | Decision | Resolution |
|---|---|---|
| D1 | Tool endpoint | **Produce model-ready inputs** (research → extract → normalize → consolidate → estimate). Model-*building* and model-*running* stay with the analyst. |
| D2 | Stage 0 mechanism | **LLM-driven each run**, expecting a specific schema document, **asking the analyst when uncertain** (no silent guessing). |
| D3 | Schema persistence | Stage 0 persists a **machine-readable schema config** (`tea-schema.json`); all deterministic scripts read it instead of hardcoded constants. |
| D4 | Two-doc division | **Scope doc** = narrative + entity decomposition + boundaries/basis/scenarios/metrics/validation. **Schema doc** = structured data spec (entities, parameters, applicability, per-parameter rule-*type*, reference targets, scope-relevance, quality tags, estimation policy). Stage 0 maps rule-types → concrete convention tables and **scaffolds** them. |
| D5 | Non-industrial test case | Design against a **named hypothetical: a managed compute / AI-inference service TEA** (cost per service unit; cost-center entities; no yield/CEPCI/per-kg). |
| D6 | Normalization | **Rule-type library dispatched by schema**: `MONETARY` / `INTENSITY` / `FRACTION` / `RATE` / `CAPEX` / `PASSTHROUGH`(+`JSON`/`TEXT`). "Functional unit" generalizes "per-kg-output"; CEPCI is one `MONETARY` index option among CPI/PPI/none. |
| D7 | Relevance gate | Each entity has a **scope frame** in the schema config. Extraction assigns `clear`/`hold`/`reject`; unresolved holds are batch-resolved and block downstream steps. |
| D8 | Reference values | **One unified pipeline + `context_free` flag.** Reference values are schema parameters searched context-free *within* master-list/gap-fill. Sources land in the unified `Sources.csv` with a role flag. |
| D9 | Estimation method | **Comparables-first** uses rubric dimensions declared by the schema. **First-principles** estimates require shown work, cited sources, and confidence. |
| D10 | Estimate sources | Populator **emits its cited sources as structured rows**; the append step registers them in `Sources.csv` with a **`source_role`** flag (`extraction`/`estimate`/`both`), **URL-only** (not downloaded). `estimate_justification` keeps the derivation but references the registered keys. |
| D11 | Model stage | **Produce inputs only; analyst runs the model.** No model execution, no back-cast inside the tool. (`run_tea_model.py`/`run_financial_model.py` are NOT generalized.) |
| D12 | Source URL column | Add **`source_url`** to **all** source-key-bearing files (Audit, Main Input, every review queue), **auto-denormalized from `Sources.csv`** whenever a `source_key` is written. `Sources.csv` stays the single source of truth. |
| D13 | Vocabulary | Code/config/CSVs use **neutral `entity` + `parameter`**; the schema doc declares a per-TEA **display label** (`process unit`, `cost center`, …) for human-facing output. |
| D14 | Numbering | **Named phases + `Phase.Stage` actions**, one discrete action per stage (§6). |
| D15 | Completeness exits | Unpopulatable cells go to estimation (Phase 6) or remain as documented gaps. |
| D16 | Comparison / build | **One system per option run** + a **comparison wrapper** for carrying shared raw evidence across options. Shared inputs are explicit mappings into option schemas and materialize as `input_origin=shared`. |

---

## 2. Architecture overview

```
  scope.md  +  data-requirements.md          (human-authored, per TEA)
        │
        ▼
  ┌─────────────────────────┐
  │ Stage 0.1  LLM compile   │ ── asks analyst when uncertain
  │  → tea-schema.json       │ ── scaffolds conventions/*.csv (empty / public-filled)
  └─────────────────────────┘
        │  (machine-readable contract)
        ▼
  ┌─────────────────────────┐
  │ Stage 0.2  build CSVs    │  Audit.csv · Sources.csv · Main Input.csv (skeleton)
  └─────────────────────────┘     + optional comparison shared inputs materialized after build
        │
        ▼     every deterministic script below READS tea-schema.json
  Phase 1 Master-list ─ Phase 2 Gap-fill ─ Phase 3 Extract ─ Phase 4 Normalize/Consolidate
        ─ Phase 5 Review ─ Phase 6 Estimate ─ Phase 7 Hand off populated inputs
```

The **schema config (`tea-schema.json`)** is the contract between the LLM
front-end (Stage 0) and the deterministic back-end (every script). No script
contains domain constants; they all dispatch off the config.

---

## 3. The two input documents

Per-TEA, human-authored, living in the run folder (§9). Templates ship in
`templates/`. Stage 0 reads both.

### 3.1 `scope.md` (narrative + decomposition)
Generalized from `TEA Framework.md` + `flowchart.md` + `unit-processes.md`.
Contains:
- **Goal & framing** — what's being analyzed and why.
- **System boundary** — upstream/downstream cut points; what's in/out of scope.
- **Functional unit** — the denominator everything is expressed per (e.g.
  `kg billet`, `1M tokens`, `delivery`). Drives `INTENSITY` normalization.
- **Entity decomposition** — the list of entities (process units / cost centers
  / activities), what each is, and how they connect (a flow description or
  diagram). This is descriptive; the machine list lives in the schema doc.
- **Basis assumptions** — currency, base year, geography, scale, financial
  params, electricity baseline, operating profile.
- **Scenarios** (optional) and **headline metrics**.
- **Validation targets** (optional) — benchmarks the analyst may use for their
  own back-cast. The tool records them; it does not run the back-cast (D11).

### 3.2 `data-requirements.md` (the schema document)
The structured spec Stage 0 compiles into `tea-schema.json`. Expected sections
(Stage 0 tolerates reasonable variation and asks when uncertain — D2):
- **Entities** — IDs, display names, one-line descriptions, output, and a
  **scope frame** per entity (`in_scope` configuration + `known_out_of_scope`
  variants) for the relevance gate (D7).
- **Parameter catalog** — for each parameter: id, label, **rule-type** (§5),
  units / numerator units, basis, `first_class` (does it justify a source on
  its own), `context_free` (reference value — search without TEA context), and
  `reference_value` (global market constant vs entity cell).
- **Applicability** — which parameters apply to which entities (default `all`,
  with per-entity overrides, e.g. yield fields only on certain entities; 1C's
  `Mg_recovery`/`Cl2_recovery`).
- **Estimation** — per-entity policy (`comparables_first` /
  `first_principles_only` / `either`) and the comparable-similarity **rubric
  dimensions** + hard-pass rule (D9).
- **Quality tags** — default A/B/C/D/E; overridable definitions.
- **Conventions needed** — declared implicitly by rule-types; Stage 0 derives
  and scaffolds the concrete tables (D4).

---

## 4. `tea-schema.json` (illustrative — Ti instance)

```jsonc
{
  "tea_id": "ti-6al-4v-incumbent",
  "display_name": "Ti-6Al-4V Incumbent Chain",
  "vocabulary": { "entity": "process unit", "parameter": "field" },
  "functional_unit": { "name": "kg Ti-6Al-4V billet", "symbol": "kg billet" },
  "basis": { "currency": "USD", "base_year": 2025,
             "inflation_index": "CEPCI", "geography": "US" },
  "quality_tags": ["A", "B", "C", "D", "E"],

  "entities": [
    { "id": "1A", "name": "Chlorination", "output": "TiCl4",
      "description": "rutile (TiO2) + carbon + Cl2 → TiCl4",
      "scope_frame": {
        "in_scope": "fluidized-bed carbochlorination of rutile to TiCl4",
        "known_out_of_scope": ["ilmenite chloride variants", "plasma chlorination"] },
      "estimation_policy": "first_principles_only" }
    // … 1B, 1C, 2A, 2B, 4, 5, 6 …
  ],

  "parameters": [
    { "id": "specific_capex", "label": "Specific CapEx", "rule_type": "CAPEX",
      "applies_to": "all", "first_class": true },
    { "id": "electricity", "label": "Electricity", "rule_type": "INTENSITY",
      "numerator_units": "kWh", "per": "entity_output",
      "applies_to": "all", "first_class": true },
    { "id": "Ti_yield", "label": "Ti yield", "rule_type": "FRACTION",
      "basis": "element-of-interest", "applies_to": ["1A","1B","4","5","6"] },
    // reference values = parameters with context_free + reference_value:
    { "id": "electricity_price", "label": "Industrial electricity price",
      "rule_type": "MONETARY", "context_free": true, "reference_value": true,
      "scope": "global", "canonical_unit": "USD/kWh",
      "market_basis": "US industrial bulk" }
  ],

  "estimation": {
    "comparable_rubric": {
      "dimensions": ["mechanism","cost_driver","scale",
                     "temperature_atmosphere","product_form_factor"],
      "hard_rule": "mechanism==match; ≤1 partial among the rest; no mismatch" } },

  "conventions_needed": ["inflation_index:CEPCI","currency_rates",
                          "unit_conversions","scaling_exponents"],
  "validation_targets": [
    { "metric": "Ti sponge $/kg", "range": [11, 12.5], "source": "Argus TG100 Sep-2025" } ]
}
```

For the **compute-service** instance the same shape holds with:
`functional_unit = "1M tokens"`, `inflation_index = "CPI"`, entities like
`compute_hardware` / `power_cooling` / `networking` / `staffing` /
`software_licensing`, no `FRACTION` yield parameters, and reference values like
`industrial_electricity_price`, `gpu_street_price`, `transit_bandwidth_price`,
`ml_engineer_loaded_rate`.

---

## 5. Normalization rule-type library (D6)

`normalize.py` dispatches on each parameter's `rule_type`:

| Rule-type | Transform | Output columns |
|---|---|---|
| `MONETARY` | → base currency (currency-rate table) → escalate to `base_year` via the declared `inflation_index` (`CEPCI`/`CPI`/`PPI`/`none`) | `normalized_value`, `normalized_units` |
| `INTENSITY` | unit-convert numerator → express per **functional unit** (or per entity output where declared) | `normalized_value`, `normalized_units` |
| `FRACTION` | coerce to dimensionless 0–1; optional basis extraction (e.g. element-of-interest) | `normalized_value` |
| `RATE` | unit-convert per-time | `normalized_value` |
| `CAPEX` | special `MONETARY`: parse to source-year USD, **carry basis-year + basis-scale**, no rebase/escalation here; QA-only `review_*` comparable | `capex_usd`, `capex_form`, `capex_basis_year`, `capex_basis_scale`, `capex_notes`, `review_*` |
| `PASSTHROUGH`/`JSON`/`TEXT` | no transform (structured/free-text fields, e.g. `stoichiometry`-like JSON, notes) | — |

Ambiguous/unparseable rows are `FLAGGED:` and routed to the Phase 4.2 queue.
Unresolved scope holds in Phase 3.2 block downstream steps until resolved.

---

## 6. The workflow (phases & one-action stages, D14)

Legend: **(L)** LLM agent · **(H)** human gate · **(S)** deterministic script.

### Phase 0 — Setup
- **0.1 Schema compile (L)** — read `scope.md` + `data-requirements.md` → emit
  `tea-schema.json`; ask the analyst on ambiguity (emit
  `schema-open-questions.md` and/or prompt interactively); scaffold the needed
  `conventions/*.csv` (empty, or auto-filled where public — CPI/CEPCI/currency).
- **0.2 Build CSVs (S)** — deterministic `build_csvs.py` reads the config →
  empty `Audit.csv`, `Sources.csv`, and `Main Input.csv` with the (entity,
  parameter) skeleton. For comparison projects, materialize shared inputs after
  each option run is built (§7).

### Phase 1 — Master-list
- **1.1 Search (L)** — broad search for high-coverage sources across
  entities×parameters; **also issues context-free sub-queries for `context_free`
  reference-value targets** (D8). Output: candidates JSON only.
- **1.2 Screen + download (H)** — analyst approves/downloads to
  `master list sources/`.
- **1.3 Normalize filenames (S)** — rename to `{entity_or_chain}_{source_key}`.
- **1.4 Register sources (S)** — append rows to `Sources.csv` (with
  `source_role=extraction`).

### Phase 2 — Gap-fill (only for entities with uncovered parameters)
- **2.1 Search per entity (L)** — targeted; ≤N candidates; URL-only locators;
  context-free sub-queries for any still-missing reference values.
- **2.2 Screen + download (H)** → `gap fill sources/`.
- **2.3 Normalize filenames (S)**.
- **2.4 Register sources (S)**.

### Phase 3 — Extraction
- **3.1 Extract per slice (L)** — one invocation per (source, coverage-slice);
  raw values + provenance + **scope-relevance status** (`clear`/`hold`/`reject`)
  vs the entity's scope frame. Batched & resumable (manifest + next-batch
  driver). No math.
- **3.2 Resolve scope-relevance holds (H)** — sweep → analyst verdicts
  (`accept`/`reject`/`re-extract`) → apply. Hard block downstream until clear.
- **3.3 Ingest to Audit (S)** — validate + append rows to `Audit.csv`.

### Phase 4 — Normalize / consolidate
- **4.1 Normalize (S)** — rule-type dispatch (§5). Hard-blocked while any
  `hold` remains.
- **4.2 Resolve normalization flags (H)** — sweep → `agent calc` / `reject` →
  normalization-agent → apply.
- **4.3 Resolve cross-source disagreements (H)** — sweep ≥30%-from-group rows →
  `accept`/`reject` → apply. Hard block on consolidate until resolved.
- **4.4 Consolidate to Main Input (S)** — per (entity, parameter): rank by
  quality tag; **scope-fit tiebreaker agent** on same-quality ties; then year /
  key fallbacks; set `selected_for_model`; compute `cross_check_delta`; write
  `Main Input.csv` (+ `source_url` denormalized, D12). Pinned cells always win
  (§7).

### Phase 5 — Review
- **5.1 Completeness review (H)** — analyst judges coverage/quality; exits:
  proceed / run another gap-fill round / accept gaps.

### Phase 6 — Estimation (fill remaining blanks)
- **6.1 Estimate (L)** — orchestrator fans out per entity: `comparables_first`
  entities run a scout (similarity rubric from the schema, D9) then a populator;
  `first_principles_only` entities go straight to **free-form-but-disciplined**
  first-principles (shown work + cited sources + confidence). Rows tagged
  `quality_tag=E`. **Cited sources emitted as rows → registered in `Sources.csv`
  with `source_role=estimate`, URL-only (D10).** `estimate_justification` JSON
  retains rubric/derivation referencing those keys.
- **6.2 Resolve held estimates (H)** — sweep all E rows → `accept` / `reject` /
  `analyst-override` (override re-tags E→D) → apply. Hard block on consolidate.
- **6.3 Normalize + re-consolidate (S)** — normalize **only** E rows
  (`--only-quality-tag E`), re-run the flag/disagreement gates for those rows,
  refresh consolidation.

### Phase 7 — Hand off
- **7.1 Finalize inputs (S)** — emit the final `Main Input.csv` + reference
  values + a run manifest (schema config, source counts, coverage, quality
  distribution, shared inputs, residual gaps). **Stop here** — the analyst runs
  their own model (D11). If `validation_targets` were declared, surface them in
  the manifest for the analyst's convenience; the tool does not back-cast.

---

## 7. Comparison shared inputs (D14, D16)

Comparison TEAs are bundles of normal option runs, not one shared route schema.
Each option keeps its own `tea-schema.json`; the comparison wrapper supplies a
shared frame and reusable raw evidence mapped explicitly into option cells.

Mechanism:

- `comparison-frame.json` declares the comparison id, display name, shared
  functional unit, shared basis, headline metrics, and option run folders.
- `shared-sources.csv` is the canonical provenance table for reusable evidence.
- `shared-inputs.csv` stores reusable raw values, units, basis fields, source
  keys, page refs, quality tags, and notes.
- `shared-input-mappings.csv` maps `shared_input_id` to
  `option_id, entity, parameter`; mappings must validate against each option
  schema.
- `scripts/materialize_shared_inputs.py` writes mapped rows into option
  `Audit.csv`/`Main Input.csv` with `relevance_status=clear` and
  `input_origin=shared`, and copies shared sources into option `Sources.csv`.
- Search, extraction, and estimation skip cells already satisfied by
  `input_origin=shared`.
- Consolidation treats shared rows as authoritative for their mapped cell while
  preserving normal normalization and provenance.

---

## 8. CSV schemas (the deterministic contract)

All defined once (from the config) and read by every script. Key changes vs
Vicky TEA in **bold**.

- **`Sources.csv`** — `source_key, authors, title, year, publisher_or_journal,
  source_url` *(renamed from `url_or_doi`; optional separate `doi`)*,
  `access_date, page_or_table_reference,` **`source_role`** *(extraction /
  estimate / both)*.
- **`Audit.csv`** — entity/parameter rows (neutral column names `entity`,
  `parameter`), raw + basis fields, quality tag, normalized/CapEx/review fields,
  `selected_for_model`, `cross_check_delta`, extractor notes, `relevance_status`
  (+ `input_origin`), the review-status columns, `estimate_justification`, **plus
  `source_url`** (denormalized).
- **`Main Input.csv`** — derived; **`source_url`** added; reference-value rows
  carried under a reserved global entity (e.g. `REF`) or `scope=global` marker.
- **Review queues** (`held_questions.csv`, `normalization_flags.csv`,
  `value_disagreements.csv`, `held_estimates.csv`, scope-fit decisions) — each
  gains **`source_url`** (D12).
- **comparison shared-input CSVs** — see §7.

A small shared helper (`source_url_for(source_key)`) denormalizes URLs from
`Sources.csv` wherever a `source_key` is written.

---

## 9. Folder structure

```
General TEA tool/
  plan.md                     ← this file
  TASKS.md                    ← actionable work breakdown (mirror of §11)
  README.md                   ← quickstart + glossary
  framework.md                ← generalized, domain-agnostic TEA framework
  workflow.md                 ← the phase/stage execution guide (§6 expanded)
  templates/
    scope.template.md
    data-requirements.template.md
    tea-schema.schema.json     ← JSON Schema the config must validate against
    shared-sources.template.csv  shared-inputs.template.csv
    shared-input-mappings.template.csv
  prompts/
    stage0-schema-compile.md
    master-list-search.md  gap-fill-search.md  extractor.md
    normalization-agent.md  scope-fit-agent.md
    estimation-orchestrator.md  estimation-scout.md  estimation-populator.md
  scripts/                     ← all config-driven; no domain constants
    build_csvs.py  rename_sources.py  register_sources.py
    extraction_manifest.py  next_batch.py  ingest_extractor_output.py
    normalize.py  consolidate.py
    sweep_*.py / apply_*.py   (holds, flags, disagreements, held-estimates)
    build_estimation_manifest.py  append_estimation_rows.py
    validate_comparison_project.py  materialize_shared_inputs.py
    finalize_comparison.py  finalize_inputs.py
    lib/  (schema loader, rule-type transforms, source_url helper, csv io)
  tests/                       ← unit + the two end-to-end fixtures
  examples/
    ti-6al-4v/                 ← ported industrial instance (regression oracle)
      scope.md  data-requirements.md  tea-schema.json  expected/Main Input.csv
    compute-service/           ← non-industrial hypothetical
      scope.md  data-requirements.md  tea-schema.json
  runs/                        ← per-run working folders (gitignored bulk)
    <run-id>/  (the two docs, schema config, working CSVs, source buckets,
               search-history/, run-manifest.md)
```

Each **run** is self-contained under `runs/<id>/` (carries its input docs +
generated config + working CSVs + history), so runs are reproducible and
diffable — the disciplined version of Vicky TEA's `Run 2/` snapshotting.

---

## 10. Validation strategy

- **Ti regression (the oracle):** the ported `examples/ti-6al-4v/` must drive
  the generalized pipeline to reproduce Vicky TEA **Run 2**'s consolidated
  result (215 Audit rows; 71/71 skeleton cells filled after estimation;
  documented selected rows). Any divergence is a generalization bug.
- **Compute smoke test:** `examples/compute-service/` must compile a valid
  `tea-schema.json`, build CSVs, and run normalize/consolidate on a small
  hand-seeded Audit with **no** `FRACTION`/`CEPCI`/per-kg paths exercised —
  proving the industrial assumptions are truly optional.
- **Unit tests** per script (schema loader, each rule-type transform, the
  source_url denormalizer, shared-input skip/selection logic, each sweep/apply).
- Carry forward the spirit of Vicky TEA's 56-test suite; expand to cover both
  fixtures.

---

## 11. Task breakdown for other agents

Dependencies form a diamond: **T1 unblocks everything**; the lane tasks (T3–T8)
share only the frozen CSV/config contract from **T1+T2** and can then proceed in
parallel; **T9–T11** integrate. Acceptance criteria are in `TASKS.md`.

| Task | Title | Depends on | Parallel-safe with |
|---|---|---|---|
| **T1** | Schema config + JSON Schema + Stage 0.1 compile prompt + clarification loop | — | — (foundational) |
| **T2** | CSV schemas + `build_csvs.py` + schema loader lib + `source_url` helper + `Sources.csv` role flag | T1 | — (foundational, with T1) |
| **T3** | Search lane: master-list + gap-fill prompts (incl. context-free reference queries), candidate JSON schema, `rename_sources.py`, `register_sources.py`, screen/download gate docs | T1, T2 | T4–T8 |
| **T4** | Extraction lane: generalized `extractor.md` w/ scope-frame, manifest + next-batch driver, `ingest_extractor_output.py`, holds sweep/apply | T1, T2 | T3, T5–T8 |
| **T5** | Normalization: rule-type library + `normalize.py` dispatcher, convention scaffolding, flags sweep/apply + normalization-agent prompt | T1, T2 | T3, T4, T6–T8 |
| **T6** | Consolidation: `consolidate.py` (config-driven ranking), scope-fit tiebreaker agent, disagreement sweep/apply, Main Input emission + `source_url` | T1, T2 | T3–T5, T7, T8 |
| **T7** | Estimation: orchestrator/scout/populator (rubric from schema; free-form FP), `build_estimation_manifest.py`, `append_estimation_rows.py`, estimate-sources→Sources.csv role flag, held-estimates sweep/apply | T1, T2 | T3–T6, T8 |
| **T8** | Comparison shared inputs: comparison frame + shared CSV contracts + validation/materialization/finalization scripts + skip/selection wiring across search/extract/estimate/consolidate + `finalize_inputs.py` | T1, T2 | T3–T7 |
| **T9** | Docs: `framework.md`, `workflow.md`, `README.md`, `templates/` (scope + data-requirements + shared-input templates) | T1 (config shape) | T3–T8 (draft early, finalize late) |
| **T10** | Worked examples: port `examples/ti-6al-4v/` (scope+schema docs + config + `expected/Main Input.csv` oracle) and author `examples/compute-service/` | T1; Ti e2e needs T3–T7 | T9 |
| **T11** | Test suite: unit tests per script + Ti regression e2e + compute smoke e2e; CI wiring | the script it tests | runs alongside each lane |

**Suggested sequencing:** T1 → T2 (foundation) → then T3–T8 in parallel, with
T9/T10/T11 drafted alongside and finalized as their dependencies land. T10's Ti
end-to-end regression is the final integration gate.

---

## 12. Assumptions I made (correct me if wrong)

- **Schema config is JSON** (`tea-schema.json`), matching the codebase's
  existing JSON manifests; a JSON Schema in `templates/` validates it.
- **Reference values** (context-free constants) live as rows in the same CSVs
  under a reserved global entity marker (`REF` / `scope=global`), not a separate
  file — that's how D8's "unified pipeline" is realized.
- **Stage 0 clarifications**: when uncertain, Stage 0 both emits a
  `schema-open-questions.md` and (if interactive) asks the analyst; it does not
  proceed past genuine ambiguity.
- **Quality tags** stay A/B/C/D/E (E = estimate; analyst-override → D), and
  `input_origin=shared` marks comparison shared inputs while
  `relevance_status` remains `clear`/`hold`/`reject`.
- **`run_tea_model.py` / `run_financial_model.py` are out of scope** (D11) and
  not ported.
- **Functional unit** is declared once in the scope doc and is the default
  `INTENSITY` denominator; parameters may override to "per entity output."

---

## 13. Open items to confirm before/during build

1. Exact `data-requirements.md` section headings (affects Stage 0 prompt
   robustness) — pin during T1 with the templates.
2. Whether the compute-service example needs its own reference-value list fleshed
   out now or can be stubbed for the smoke test (T10).
3. Naming: `entity`/`parameter` confirmed for code; confirm the Ti display
   labels (`process unit`/`field`) read well in outputs (T9).
4. Minimum candidate caps / batch sizes per phase — carry Vicky TEA defaults
   (≤15 master-list, ≤5 gap-fill, ≤8 extraction batch) unless the schema
   overrides.
