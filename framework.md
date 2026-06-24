# General TEA Framework

This framework describes how to express a techno-economic analysis so the
General TEA Tool can research, extract, normalize, consolidate, and hand off
model-ready inputs. It is intentionally narrower than a full TEA methodology:
the analyst owns the model and the economic interpretation; the tool owns the
input-population pipeline.

## Boundary Of The Tool

The tool starts after the analyst has a model shape in mind and can specify the
data it needs. It ends when `Main Input.csv`, `Reference Values.csv`, and a run
manifest are ready. It does not construct a process model, financial model,
scenario engine, or back-cast.

One run represents one system or configuration. Comparisons across systems are
handled by a comparison wrapper containing separate option runs, shared raw
evidence, and explicit mappings into each option schema.

## Core Objects

An entity is a scoped part of the system: a process unit, cost center, activity,
equipment group, logistics leg, or other model component. Each entity needs a
stable id, a human name, a concise description, and a scope frame.

A parameter is a field the model needs. Parameters declare their normalization
rule type and the entities they apply to. A parameter may apply to every entity,
to a listed subset, or to the reserved global entity `REF` when it is a
reference value.

The functional unit is the denominator for model-ready values. Examples include
`kg Ti-6Al-4V billet`, `1M tokens served`, or `delivery`. It is the default
denominator for `INTENSITY` parameters unless the parameter explicitly uses
`entity_output`.

The basis records the currency, base year, inflation index, and geography used
for normalization. Industrial settings may use CEPCI and per-kg outputs; other
domains may use CPI, PPI, or no inflation index and a different functional
unit.

## Rule Types

`MONETARY` parameters are recurring or market price figures that normalize to
the configured currency and base year.

`INTENSITY` parameters are quantities per functional unit or per entity output.

`FRACTION` parameters normalize to dimensionless values from 0 to 1.

`RATE` parameters normalize per-time flows or throughput values.

`CAPEX` parameters carry capital costs as source-year currency with basis
scale, basis year, and review fields. They are not escalated during ordinary
normalization.

`PASSTHROUGH`, `JSON`, and `TEXT` parameters carry values or notes without
numeric normalization.

If a parameter could fit more than one rule type, the data-requirements document
should spell out the intended basis. Stage 0 records unresolved ambiguity as an
open question instead of guessing.

## Scope And Relevance

Every entity has a scope frame:

- `in_scope`: the configuration, technology, market, or service variant the
  run actually represents.
- `known_out_of_scope`: named variants that should not contaminate the run.

During extraction, each value is labeled `clear`, `hold`, or `reject`. Held
rows are reviewed by the analyst before normalization can proceed. Comparison
shared inputs use `input_origin=shared` with `relevance_status=clear` and are
treated as authoritative for their mapped cells.

## Evidence And Quality

`Sources.csv` is the source registry. Each source has a stable `source_key`, a
canonical `source_url`, and a `source_role` of `extraction`, `estimate`, or
`both`.

`Audit.csv` is the evidence ledger. It contains raw values, source provenance,
quality tags, normalized values, review statuses, estimate justification, and
the final `selected_for_model` flag.

Quality tags are ordered best to worst by the schema. The default set is
`A`, `B`, `C`, `D`, `E`, where `E` is reserved for estimates and analyst
overrides of estimates become `D`.

## Reference Values

Reference values are market or background constants that belong to the TEA as a
whole, not to a real entity. They are declared as normal parameters with
`reference_value: true`, `context_free: true`, and `scope: "global"`.

Searches for reference values must not mention the TEA system. For example,
search for an industrial electricity price as an electricity market value, not
as a price for a titanium or compute-service TEA.

## Estimation

Estimation fills remaining blanks after search, extraction, normalization,
consolidation, and review. Each entity declares one policy:

- `comparables_first`: scout for comparable systems using the schema rubric,
  then populate estimates.
- `first_principles_only`: skip comparable scouting and show the derivation.
- `either`: allow either method if the evidence supports it.

Estimates must cite structured sources, show work, and carry confidence and
justification. They are reviewed before they can be normalized and consolidated.

## Human Gates

The tool is deterministic where it can be and explicit where judgment is
required. Human gates occur at source screening, scope-hold resolution,
normalization flags, value disagreements, completeness review, held estimates,
and optional analyst overrides.

These gates are not clerical ceremony. They protect the run from wrong
boundaries, mismatched units, weak sources, and plausible-looking estimates
that do not belong in the model.

The run's setup-time `execution_mode` controls who resolves these gates.
`auto_with_human_gates` is the default and pauses for the analyst. `auto` uses
the AI as the gate operator, records each decision and rationale, continues
through ambiguity, and surfaces assumptions, flags, and technical errors at the
end. Auto cannot finalize until every TEA cell has one finite numeric value.
Auto also treats evidence accessibility as an eligibility requirement: search
and estimation may use only relevant evidence that is openly inspectable,
rather than paywalled, login-only, purchase-only, or request-access material.

## Final Hand-Off

The final artifacts are:

- `Main Input.csv`: selected model-ready cells.
- `Reference Values.csv`: global `REF` rows split out for convenience.
- `run-manifest.md`: coverage, quality distribution, source counts, shared
  inputs, residual gaps, and validation targets.

Validation targets are surfaced for the analyst's convenience. The tool does
not run the model or judge whether the TEA result passes those targets.
