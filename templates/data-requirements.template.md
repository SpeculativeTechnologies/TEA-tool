# Data Requirements

Use this document to specify the machine-readable data contract in human form.
Stage 0 compiles it with `scope.md` into `tea-schema.json`. Be explicit about
units, rule types, applicability, and estimation policy.

## 1. Schema Identity

- TEA id:
- Display name:
- Entity display label:
- Parameter display label:
- Quality tag order: A, B, C, D, E

Quality tag meanings:

| tag | definition |
|---|---|
| A |  |
| B |  |
| C |  |
| D |  |
| E | Estimate generated in Phase 6 |

## 2. Basis

- Functional unit name:
- Functional unit symbol:
- Base currency:
- Base year:
- Inflation index: CEPCI, CPI, PPI, or none
- Geography:

## 3. Entities

Each entity must have an id, name, output, scope frame, and estimation policy.
Allowed estimation policies: `comparables_first`, `first_principles_only`,
`either`.

| id | name | output | estimation_policy | description |
|---|---|---|---|---|
|  |  |  |  |  |

### Scope Frames

| entity id | in_scope | known_out_of_scope |
|---|---|---|
|  |  |  |

Use semicolons inside `known_out_of_scope` if several variants are listed.

## 4. Parameter Catalog

Allowed rule types:

- `MONETARY`: price or recurring money figure normalized to base currency/year.
- `INTENSITY`: physical or service quantity per functional unit or entity
  output.
- `FRACTION`: ratio, yield, recovery, efficiency, or utilization from 0 to 1.
- `RATE`: per-time throughput or flow.
- `CAPEX`: capital cost carried with basis year and scale.
- `PASSTHROUGH`: value carried without numeric transform.
- `JSON`: structured machine data carried verbatim.
- `TEXT`: free-form notes.

| parameter id | label | rule_type | applies_to | search_targetable | units | numerator_units | per | canonical_unit | basis | description |
|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  | all or entity ids | true/false |  |  | functional_unit or entity_output |  |  |  |

Guidance:

- Use `search_targetable=true` when the parameter justifies its own source search.
- For `INTENSITY`, provide `numerator_units` and `per`.
- For `RATE`, provide `units`.
- For `FRACTION`, state the basis if relevant.
- For `CAPEX`, state `capex_form` in the notes or description if needed.
- If a parameter applies only to some entities, list their ids.

## 5. Reference Values

Reference values are global market/background constants. They are searched
without TEA context and stored under entity `REF`.

Every reference value must have:

- `reference_value=true`
- `context_free=true`
- `scope=global`
- `canonical_unit`
- `market_basis`

| parameter id | label | rule_type | canonical_unit | market_basis | notes |
|---|---|---|---|---|---|
|  |  | MONETARY |  |  |  |

Examples: industrial electricity price, GPU street price, transit bandwidth
price, loaded labor rate.

## 6. Applicability Exceptions

Use this section if the parameter catalog is easier to read with defaults plus
exceptions.

| parameter id | applies_to | does_not_apply_to | reason |
|---|---|---|---|
|  |  |  |  |

## 7. Estimation Policy

For every entity, explain how remaining blanks should be estimated after
research and extraction.

| entity id | policy | notes |
|---|---|---|
|  | comparables_first, first_principles_only, or either |  |

If any entity uses `comparables_first` or `either`, define the comparable
rubric.

Comparable rubric dimensions:

- 

Hard-pass rule:

## 8. Conventions Needed

Stage 0 can derive convention files from rule types, but list known needs here
so omissions are obvious.

- Inflation index file: CEPCI, CPI, PPI, or none
- Currency rates:
- Unit conversions:
- Scaling exponents:
- Other:

## 9. Search Defaults

Optional. Leave blank to use defaults.

- Master-list candidate cap:
- Gap-fill candidate cap:
- Extraction batch size:

## 10. Comparison Shared Inputs

If this TEA is part of a comparison project, list assumptions that might be
shared through the comparison wrapper. Leave blank for a standalone run.

- Candidate shared assumptions:
- Option-specific exceptions:
- Reuse rationale:

## 11. Open Questions For Stage 0

List anything Stage 0 should ask rather than infer.

- 
