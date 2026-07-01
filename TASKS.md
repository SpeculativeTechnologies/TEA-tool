# General TEA Tool — Task Board

Pickup-able work units for the build described in [`plan.md`](plan.md). Each
task is self-contained: an agent should be able to claim one, read the
referenced material, and deliver without further context.

**Conventions for every task**
- Build target: `C:\Users\danie\Speculative Technologies\General TEA tool\`.
- Reference (read, do **not** edit): `..\Vicky TEA\` — its `plan.md`,
  `workflow.md`, `prompts/`, `scripts/`, `conventions/`, and `Run 2/`.
- **Fresh rewrite** (decision D16): treat Vicky TEA code as reference, not a
  base to copy. All new scripts are **config-driven** — they read
  `tea-schema.json`, never hardcode entities/parameters/conventions.
- Neutral vocabulary in code: `entity`, `parameter` (D13).
- Any file that writes a `source_key` must also write `source_url` (D12).
- Add/extend tests in `tests/` for whatever you build (T11 owns the harness).

Status keys: ☐ todo · ◐ in progress · ☑ done. Claim by putting your agent
id/initials next to the task and flipping to ◐.

---

## T1 — Schema config + Stage 0 compile  ☑  *(foundational, blocks all)*

> **Done.** `templates/tea-schema.schema.json` (JSON Schema, Draft 2020-12),
> `scripts/lib/schema.py` (loader + `Schema` accessor + `validate_schema`,
> jsonschema-with-builtin-fallback), `prompts/stage0-schema-compile.md`.
> Validated Ti + compute config fixtures live in `tests/fixtures/`; 34 unit
> tests in `tests/test_schema.py` (green). Downstream lanes import via
> `from lib.schema import load_schema, Schema` (run scripts as `python
> scripts/<x>.py` so `scripts/` is on the path). `jsonschema` is optional
> (`requirements-dev.txt`); the builtin validator mirrors the contract.

**Goal:** define the `tea-schema.json` contract and the LLM step that produces
it from the two input docs.

**Deliverables**
- `templates/tea-schema.schema.json` — JSON Schema for the config (entities w/
  scope_frame + estimation_policy; parameters w/ rule_type ∈
  {MONETARY,INTENSITY,FRACTION,RATE,CAPEX,PASSTHROUGH,JSON,TEXT}, applies_to,
  search_targetable, context_free, reference_value, scope; basis w/ inflation_index ∈
  {CEPCI,CPI,PPI,none}; functional_unit; estimation.comparable_rubric;
  conventions_needed; validation_targets). See plan.md §4 for the shape.
- `prompts/stage0-schema-compile.md` — reads `scope.md` + `data-requirements.md`
  → emits `tea-schema.json`; **asks the analyst when uncertain** (emits
  `schema-open-questions.md` and/or prompts interactively — D2); derives
  `conventions_needed` from rule-types and scaffolds empty/public-filled
  `conventions/*.csv` (D4).
- `lib/schema.py` — loader + validator used by every downstream script.

**Acceptance**
- The Ti and compute example docs (T10) both compile to configs that validate
  against the JSON Schema.
- Ambiguous input (e.g. a parameter with no declared units) yields a logged
  open question, not a silent default.

---

## T2 — CSV schemas + builder + shared libs  ☑  *(foundational, with T1)*

> **Done.** `scripts/lib/csvio.py` defines the stable CSV schemas and shared
> read/write helpers; `scripts/lib/source_url.py` provides the `source_url_for`
> denormalizer; `scripts/build_csvs.py` builds config-driven `Audit.csv`,
> `Sources.csv`, and `Main Input.csv` skeletons from `Schema.skeleton_cells()`,
> including `REF` reference-value rows and `input_origin` columns. T2 coverage
> lives in `tests/test_csv_contract.py`; full suite green at 48 tests
> (`python -m unittest discover -s tests`, 2 optional jsonschema skips).

**Goal:** the deterministic CSV contract and the empty-file builder.

**Deliverables**
- `scripts/build_csvs.py` — reads the config → empty `Audit.csv`,
  `Sources.csv`, `Main Input.csv` (with the entity×parameter skeleton, incl.
  reference-value rows under the reserved global entity). Loads
  comparison shared inputs are materialized separately by T8.
- CSV schemas per plan.md §8, incl. `Sources.csv` `source_url` (renamed from
  `url_or_doi`) + `source_role`; `source_url` on Audit/Main Input/queues.
- `lib/source_url.py` — `source_url_for(source_key)` denormalizer.
- `lib/csvio.py` — shared read/write with stable column ordering.

**Reference:** Vicky TEA `scripts/build_csvs.py` (note the hardcoded
`UNITS`/`COMMON_FIELDS`/`YIELD_FIELDS_BY_UNIT`/`CONSUMABLES_BY_UNIT` — these
become config-driven here).

**Acceptance:** building from the Ti config reproduces the Run 2 skeleton
shape; building from the compute config produces a valid skeleton with no
yield/CapEx-CEPCI columns required.

---

## T3 — Search lane  ☑  *(needs T1, T2)*

> **Done.** `prompts/master-list-search.md` and
> `prompts/gap-fill-search.md` are schema-driven and use neutral
> `entity`/`parameters` coverage with context-free reference-value subqueries.
> `templates/search-candidates.schema.json` defines the structural candidate
> JSON contract; `scripts/lib/search.py` validates coverage against
> `Schema.applies()`, rejects TEA-context reference queries, and provides
> source-file matching helpers. `scripts/rename_sources.py` normalizes approved
> downloads to `{entity_or_chain}_{source_key}.{ext}`; `scripts/register_sources.py`
> appends approved candidates to `Sources.csv` with `source_role=extraction` and
> `source_url`. Search-lane human gates are scaffolded in `workflow.md`. T3
> coverage lives in `tests/test_search_lane.py`; full suite green at 54 tests
> (`python -m unittest discover -s tests`, 2 optional jsonschema skips).

**Goal:** master-list + gap-fill search, generalized, with folded-in
context-free reference-value search (D8).

**Deliverables**
- `prompts/master-list-search.md` — config-driven (entities×parameters from the
  schema, not a hardcoded unit table). **Issues context-free sub-queries for
  `context_free` reference-value targets** ("must not mention the TEA/system").
  Candidate JSON schema.
- `prompts/gap-fill-search.md` — per-entity targeted search; URL-only locators;
  ≤N cap from config (default 5); search-targetable-parameter eligibility from config.
- `scripts/rename_sources.py` — filename normalization to
  `{entity_or_chain}_{source_key}.{ext}` (config-aware).
- `scripts/register_sources.py` — append candidates to `Sources.csv` with
  `source_role=extraction` (+ `source_url`).
- Screen/download human-gate docs in `workflow.md` (coordinate with T9).

**Reference:** Vicky TEA `prompts/master-list-search.md`,
`prompts/gap-fill-search.md`, `prompts/constants-search.md` (fold its
context-free discipline in), `scripts/rename_sources_from_json.py`,
`scripts/populate_sources.py`.

**Acceptance:** for the Ti config, a search run produces candidate JSON whose
`field_coverage` references only valid schema (entity, parameter) pairs;
reference-value sub-queries carry no TEA context.

---

## T4 — Extraction lane  ☑  *(needs T1, T2)*

> **Done.** `prompts/extractor.md` is schema-driven, raw-values-only, and uses
> per-entity `scope_frame` for `clear`/`hold`/`reject` relevance decisions.
> `scripts/extraction_manifest.py` builds accepted-source extraction slices
> from search JSON + `Sources.csv`; `scripts/next_batch.py` returns resumable
> batches using the schema default size. `scripts/ingest_extractor_output.py`
> validates entity/parameter applicability, mandatory `page_ref`, hold/reject
> shape, and denormalizes `source_url` into `Audit.csv`.
> `scripts/sweep_held_questions.py` and `scripts/apply_held_verdicts.py`
> provide the hold queue/apply flow, with `lib.extraction.assert_no_unresolved_holds`
> as the downstream hard-block hook. T4 coverage lives in
> `tests/test_extraction_lane.py`; full suite green at 62 tests
> (`python -m unittest discover -s tests`, 2 optional jsonschema skips).

**Goal:** per-slice extraction with the generalized scope-relevance gate (D7).

**Deliverables**
- `prompts/extractor.md` — raw-values-only; mandatory `page_ref`; emits
  `relevance_status` (`clear`/`hold`/`reject`) by checking each value against
  the **entity scope_frame** from the config (not a Ti `incumbent-route.csv`).
- `scripts/extraction_manifest.py` + `scripts/next_batch.py` — resumable batch
  driver (≤8/slice default).
- `scripts/ingest_extractor_output.py` — validate + append to `Audit.csv`.
- `scripts/sweep_held_questions.py` + `scripts/apply_held_verdicts.py` —
  holds resolution (+ `source_url` in the queue).

**Reference:** Vicky TEA `prompts/extractor.md`, `scripts/stage3_next_batch.py`,
`scripts/ingest_extractor_output.py`, `scripts/sweep_held_questions.py`,
`scripts/apply_held_verdicts.py`, `conventions/incumbent-route.csv`.

**Acceptance:** the hard block holds (normalize refuses while any `hold`
remains); a Ti slice reproduces its Run 2 extracted rows.

---

## T5 — Normalization  ☑  *(needs T1, T2)*

> **Done.** `scripts/lib/transforms.py` implements schema-dispatched rule-type
> transforms for `MONETARY`, `INTENSITY`, `FRACTION`, `RATE`, `CAPEX`,
> `PASSTHROUGH`, `JSON`, and `TEXT`; `scripts/normalize.py` hard-blocks
> unresolved extraction holds, supports `--only-quality-tag E`, and preserves
> `source_url`. `scripts/scaffold_conventions.py` creates required
> `conventions/*.csv` files with base-year currency/index anchors and unit
> conversion seeds. `scripts/sweep_normalization_flags.py`,
> `scripts/apply_normalization_flags.py`, and `prompts/normalization-agent.md`
> provide the Phase 4.2 review flow. T5 coverage lives in
> `tests/test_normalization.py`; full suite green at 68 tests
> (`python -m unittest discover -s tests`, 2 optional jsonschema skips).

**Goal:** the rule-type library + dispatcher (D6, plan.md §5).

**Deliverables**
- `lib/transforms.py` — one transform per rule-type (MONETARY w/ configurable
  inflation index incl. CEPCI/CPI/PPI/none; INTENSITY w/ functional-unit
  denominator; FRACTION; RATE; CAPEX w/ basis carry + review_*; PASSTHROUGH).
- `scripts/normalize.py` — dispatches per parameter's `rule_type`; `FLAGGED:`
  ambiguous rows; `--only-quality-tag E` mode for Phase 6.3; hard block on
  unresolved holds.
- Convention scaffolding (`conventions/*.csv`) + auto-fill of public indices.
- `scripts/sweep_normalization_flags.py` + `apply_normalization_flags.py` +
  `prompts/normalization-agent.md`.

**Reference:** Vicky TEA `scripts/normalize.py`, `conventions/cepci.csv`,
`currency-rates.csv`, `unit-conversions.csv`, `prompts/normalization-agent.md`.

**Acceptance:** Ti rows normalize to the same values as Run 2; a compute
`MONETARY` row escalates via CPI with **no** CEPCI/per-kg path touched.

---

## T6 — Consolidation  ☑  *(needs T1, T2)*

> **Done.** `scripts/consolidate.py` ranks normalized Audit rows by shared
> status, schema quality tags, scope-fit decisions, raw basis year, and
> `source_key`; writes consolidated Audit sidecars and schema-complete
> `Main Input.csv` rows with `source_url`; and blocks unresolved value
> disagreements plus unreviewed E rows. `prompts/scope-fit-agent.md` generalizes
> the route-fit tiebreaker around each entity `scope_frame`.
> `scripts/sweep_value_disagreements.py` and
> `scripts/apply_value_disagreements.py` provide the Phase 4.3 queue/apply
> flow with `source_url`. T6 coverage lives in `tests/test_consolidation.py`;
> full suite green at 72 tests (`python -m unittest discover -s tests`, 2
> optional jsonschema skips).

**Goal:** select the best row per cell and emit Main Input (D12, plan.md §6.4).

**Deliverables**
- `scripts/consolidate.py` — config-driven ranking (quality tag → scope-fit
  tiebreaker → year → key); `selected_for_model`; `cross_check_delta`; writes
  `Main Input.csv` with `source_url`. Pinned cells always win (coordinate w/ T8).
- `prompts/scope-fit-agent.md` — generalized route-fit tiebreaker against the
  entity scope_frame.
- `scripts/sweep_value_disagreements.py` + `apply_value_disagreements.py`
  (≥30% group deviation; `source_url` in queue).

**Reference:** Vicky TEA `scripts/consolidate.py`,
`prompts/stage5-route-fit-agent.md`, `scripts/sweep_value_disagreements.py`,
`scripts/apply_value_disagreements.py`.

**Acceptance:** Ti consolidation reproduces Run 2's selected rows + filled-cell
count.

---

## T7 — Estimation  ☑  *(needs T1, T2)*

> **Done.** `prompts/estimation-orchestrator.md`,
> `prompts/estimation-scout.md`, and `prompts/estimation-populator.md` are
> schema-driven, route by each entity's `estimation_policy`, and require the
> comparable rubric dimensions/hard rule from `tea-schema.json`.
> `scripts/build_estimation_manifest.py` emits currently blank eligible cells
> grouped by entity (including `REF` reference values) and carries existing
> real extractions as anchors. `scripts/append_estimation_rows.py` validates E
> rows, registers structured cited sources into `Sources.csv` with
> `source_role=estimate`/`both`, denormalizes `source_url`, and supports
> idempotent/force-refresh appends. `scripts/sweep_held_estimates.py` and
> `scripts/apply_held_estimates.py` provide accept/reject/analyst-override
> review, with overrides re-tagged to D. T7 coverage lives in
> `tests/test_estimation_lane.py`; full suite green at 79 tests
> (`python -m unittest discover -s tests`, 2 optional jsonschema skips).

**Goal:** comparables-first + free-form first-principles, with estimate sources
registered (D9, D10).

**Deliverables**
- `prompts/estimation-orchestrator.md` — fan-out per entity; routes by
  `estimation_policy`; mechanical validation only.
- `prompts/estimation-scout.md` — comparable discovery + **rubric from the
  config** (dimensions + hard rule), not hardcoded industrial dims.
- `prompts/estimation-populator.md` — comparable-mode OR **free-form-but-
  disciplined** first-principles (shown work + cited sources + confidence; no
  prescribed method library). **Emits cited sources as structured rows.**
- `scripts/build_estimation_manifest.py` — currently-blank eligible cells.
- `scripts/append_estimation_rows.py` — writes E rows **and registers their
  cited sources in `Sources.csv` with `source_role=estimate` (URL-only)**;
  `estimate_justification` references those keys.
- `scripts/sweep_held_estimates.py` + `apply_held_estimates.py`
  (accept/reject/analyst-override→D).

**Reference:** Vicky TEA `prompts/estimation-*.md`,
`scripts/build_estimation_manifest.py`, `scripts/append_estimation_rows.py`,
`scripts/sweep_held_estimates.py`, `scripts/apply_held_estimates.py`.

**Acceptance:** an E row's cited sources appear in `Sources.csv` flagged
`estimate`; the comparable rubric is read from the config (swapping rubric
dimensions in the config changes the scout's scoring fields).

---

## T8 — Comparison shared inputs  ☑  *(needs T1, T2)*

> **Done.** Comparison projects use `comparison-frame.json`,
> `shared-sources.csv`, `shared-inputs.csv`, and
> `shared-input-mappings.csv`. `scripts/validate_comparison_project.py`
> validates wrapper contracts; `scripts/materialize_shared_inputs.py` writes
> mapped rows with `input_origin=shared`; `scripts/finalize_comparison.py`
> emits comparison-level summaries. Search validation, extraction manifests,
> estimation manifests, consolidation, and finalization recognize shared
> satisfied cells. T8 coverage lives in `tests/test_shared_inputs.py` plus lane
> tests.

**Goal:** reuse raw evidence across normal option runs while each option keeps
its own route schema (plan.md §7).

**Deliverables**
- Shared CSV templates for sources, reusable inputs, and explicit mappings.
- `scripts/validate_comparison_project.py` — validate frame, option schemas,
  basis/functional-unit match, source references, and mappings.
- `scripts/materialize_shared_inputs.py` — materialize `input_origin=shared`
  Audit/Main Input rows and copy shared sources into option `Sources.csv`.
- Skip wiring: search (T3), extraction manifest (T4), estimation manifest (T7),
  consolidation (T6), and finalization recognize shared cells.
- `scripts/finalize_comparison.py` — emit `shared-assumptions.csv`,
  `option-summary.csv`, and `comparison-manifest.md`.

**Acceptance:** a shared input is normalized inside each mapped option, selected
as authoritative for that cell, skipped by search/extraction/estimation, and
reported in option and comparison manifests.

---

## T9 — Docs & templates  ☑  *(needs T1 shape; finalize late)*

> **Done.** `framework.md` now explains the domain-agnostic TEA framing,
> boundaries, evidence model, rule types, reference values, estimation,
> comparison shared inputs, and hand-off. `workflow.md` is expanded into a full Phase 0-7
> operator guide with concrete run-folder commands and human-gate instructions.
> `README.md` provides quickstart, outputs, glossary, and test entrypoint.
> `templates/scope.template.md` and `templates/data-requirements.template.md`
> give new analysts the sections and tables needed to author the two Stage 0
> input docs without reading the Ti example.

**Deliverables:** `framework.md` (generalized, domain-agnostic — derived from
Vicky TEA `TEA Framework.md`), `workflow.md` (plan.md §6 expanded into an
execution guide with human-gate instructions), `README.md` (quickstart +
glossary), `templates/scope.template.md`, `templates/data-requirements.template.md`.

**Acceptance:** a new analyst can author both input docs from the templates
without reading the Ti example.

---

## T10 — Worked examples  ☑  *(needs T1; Ti e2e needs T3–T7)*

> **Done.** `examples/ti-6al-4v/` now contains human-authored `scope.md` and
> `data-requirements.md`, a validated `tea-schema.json` aligned with the Ti
> fixture, and `expected/Main Input.csv` copied from Victoria Chernow TEA
> `Run 2` as the regression oracle. `examples/compute-service/` now contains
> its scope, data-requirements doc, and validated non-industrial schema. T10
> coverage lives in `tests/test_examples.py`; full suite green at 91 tests
> (`python -m unittest discover -s tests`).

**Deliverables**
- `examples/ti-6al-4v/` — `scope.md`, `data-requirements.md` (re-expressing the
  Ti case in the new format), the compiled `tea-schema.json`, and
  `expected/Main Input.csv` lifted from Vicky TEA `Run 2/Main Input.csv` as the
  **regression oracle**.
- `examples/compute-service/` — `scope.md`, `data-requirements.md`,
  `tea-schema.json` for the managed compute/AI-inference archetype (plan.md §4):
  cost-center entities, `1M tokens` functional unit, CPI index, reference values
  (electricity, GPU street price, transit bandwidth, loaded labor rate), no
  yield/CapEx-CEPCI.

**Acceptance:** Ti example drives the full pipeline to reproduce Run 2's
consolidated result; compute example compiles + builds + smoke-normalizes.

---

## T11 — Test suite  ☑  *(runs alongside every lane)*

> **Done.** The suite now has a single unittest entrypoint:
> `python -m unittest discover -s tests`. Coverage includes unit tests for the
> schema loader/validator, CSV contracts, source URL denormalization, search,
> extraction, normalization transforms and queues, consolidation/disagreement
> gates, estimation, shared inputs/finalization, worked examples, and T11
> deterministic end-to-end fixtures. `tests/test_end_to_end.py` wires build →
> normalize → consolidate → finalize for the compute smoke case and runs a Ti
> legacy-oracle regression projection against `examples/ti-6al-4v/expected/Main Input.csv`,
> with structural v1 rewrite deltas documented in the test. Full suite green at
> 93 tests (`python -m unittest discover -s tests`).

**Deliverables:** unit tests (schema loader/validator, each rule-type transform,
`source_url` denormalizer, shared-input skip/selection predicate, every sweep/apply),
plus two end-to-end fixtures — **Ti regression** (oracle = `examples/ti-6al-4v/
expected/Main Input.csv`) and **compute smoke** (no industrial path exercised).
Wire a single `python -m pytest` (or unittest) entrypoint.

**Acceptance:** green suite; Ti e2e diff against the oracle is empty (modulo
documented, justified deltas); compute smoke passes without loading any
industrial transform.

---

## Critical path

```
T1 ─┬─ T2 ─┬─ T3 ┐
    │      ├─ T4 ┤
    │      ├─ T5 ┤
    │      ├─ T6 ┼─→ T10 (Ti e2e regression) ─→ done
    │      ├─ T7 ┤
    │      └─ T8 ┘
    └─ T9 (docs, parallel)         T11 (tests, parallel throughout)
```

T1+T2 are the foundation. T3–T8 parallelize once the config + CSV contract is
frozen. T10's Ti end-to-end regression is the final integration gate.
