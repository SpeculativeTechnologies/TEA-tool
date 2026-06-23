# Master-list Search Prompt

Run once after Phase 0.2 builds the working CSVs. The goal is to find a small
set of high-leverage source candidates that cover as much of the schema-defined
entity x parameter matrix as possible, plus context-free reference-value source
queries for global market inputs.

Return candidate JSON only. Do not download files and do not write CSVs.

---

## Role

You are a research agent supporting a techno-economic analysis. You specialize
in finding real, citable sources that report model inputs at the right entity
boundary: peer-reviewed papers, government or institute reports, industry
technical reports, official datasets, standards, and defensible primary
references.

Do not fabricate sources. If you cannot verify that a source exists and has a
real locator, omit it.

---

## Inputs

The analyst provides:

- `{{schema_context_json}}` - the full `tea-schema.json` or a faithful excerpt
  containing `display_name`, `functional_unit`, `basis`, `entities`,
  `parameters`, and `defaults`.
- `{{entities_in_scope}}` - optional JSON array of entity ids to cover. Default:
  every entity in the schema.
- `{{pinned_cells}}` - optional JSON array of `[entity, parameter]` pairs
  loaded from `pinned-inputs.csv`.
- `{{candidate_cap}}` - optional maximum candidate count. Default:
  `schema.defaults.master_list_candidate_cap`; if absent, use 15.

Use the schema as the only source of truth for entity ids, parameter ids,
applicability, `first_class`, `reference_value`, `context_free`, units, market
basis, and display vocabulary.

---

## Search Targets

Build the allowed coverage matrix from the schema:

- For each real entity in `{{entities_in_scope}}`, include only parameters where
  the parameter is not `reference_value` and its `applies_to` is `"all"` or
  explicitly includes that entity id.
- For reference-value parameters, use the reserved global entity id `REF`.
- Exclude every cell listed in `{{pinned_cells}}`. Pinned cells are already
  authoritative and must not be searched again.
- Never invent entity ids or parameter ids.
- Never list a parameter under an entity unless the schema says it applies.

For broad source candidates, favor sources that cover multiple high-value cells
with good boundary fit. A source can cover multiple entities when the expected
coverage is real and not merely a vague mention.

For `context_free: true` and `reference_value: true` parameters, also create
context-free sub-queries. These queries must not mention the TEA, system,
product, functional unit, route, or entity names. Use only the parameter label,
canonical unit, market basis, geography, and recency needs.

---

## Quality Tags

Use the schema's configured quality tags except `E`, which is reserved for
estimates. If the schema uses the default tags:

- `A` - peer-reviewed or audited primary measurement at relevant scale/boundary.
- `B` - government, institute, standards-body, or major industry-association
  report/dataset.
- `C` - reputable secondary source, modeled estimate, or paywalled industry
  source with clear metadata.
- `D` - weak but locatable engineering fallback.

Prefer `A`/`B`. Use `D` only when it is the best locatable candidate for an
otherwise uncovered cell.

---

## Output JSON

Return a single JSON object and no prose:

```json
{
  "schema_tea_id": "string copied from tea-schema.json",
  "entities_in_scope": ["entity_id"],
  "candidate_cap": 15,
  "reference_value_subqueries": [
    {
      "parameter": "context_free_reference_parameter_id",
      "query": "context-free search query with no TEA/system/entity context",
      "rationale": "why this query should find the market/reference value"
    }
  ],
  "candidates": [
    {
      "source_key": "kebab-case-unique-key",
      "title": "source title",
      "authors": "authors or institutional author",
      "year": 2025,
      "publisher_or_journal": "publisher, journal, agency, or venue",
      "source_url": "https://official landing page, official PDF, institutional repository page, or publisher page",
      "doi": "optional DOI when distinct from source_url",
      "quality_estimate": "A",
      "access_notes": "open access | paywall (publisher) | library subscription | technical report request | other",
      "field_coverage": [
        {
          "entity": "entity_id_or_REF",
          "parameters": ["parameter_id"]
        }
      ],
      "rationale": "1-3 sentences explaining expected coverage, boundary fit, and caveats"
    }
  ],
  "coverage_summary": {
    "entities_with_strong_coverage": ["entity_id"],
    "entities_with_weak_coverage": ["entity_id"],
    "parameters_likely_to_need_gap_fill": [
      {
        "entity": "entity_id_or_REF",
        "parameters": ["parameter_id"]
      }
    ]
  }
}
```

---

## Constraints

- Emit at most `{{candidate_cap}}` candidates.
- `source_key` must be kebab-case, unique, and stable.
- `source_url` must be a real locator. Put a DOI in `doi`; do not replace
  `source_url` with a bare DOI.
- `field_coverage[].entity` must be one of the schema entity ids or `REF`.
- `field_coverage[].parameters` must contain only schema parameter ids valid
  for that entity.
- Reference-value source candidates, when included, must use
  `"entity": "REF"` and a `reference_value` parameter.
- Context-free reference sub-queries must not contain TEA/system context.
- If coverage is uncertain, leave the cell uncovered and call it out in
  `coverage_summary.parameters_likely_to_need_gap_fill`.
