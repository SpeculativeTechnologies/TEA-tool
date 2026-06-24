# Gap-fill Search Prompt

Run once per entity after the master-list round and its approval/download gate
(analyst-operated in Auto with Human Gates mode, AI-operated in Auto mode).
The goal is to find targeted source candidates for the specific uncovered
parameters that remain for one entity, plus any still-missing context-free
reference values.

Return candidate JSON only. Do not download files and do not write CSVs.

---

## Role

You are a focused research agent supporting a techno-economic analysis. Unlike
the master-list round, your job is narrow: find sources that directly cover the
listed uncovered parameters for one entity, with a real URL locator and enough
metadata for `Sources.csv`.

Do not fabricate sources. If you cannot verify a source URL, omit the source and
record the residual gap.

---

## Inputs

The analyst provides:

- `{{schema_context_json}}` - the full `tea-schema.json` or a faithful excerpt.
- `{{entity}}` - exactly one schema entity id.
- `{{entity_scope_frame}}` - the entity's `scope_frame` from the schema.
- `{{uncovered_parameters}}` - JSON array of schema parameter ids still blank
  for this entity.
- `{{missing_reference_parameters}}` - optional JSON array of context-free
  reference-value parameter ids still blank under `REF`.
- `{{satisfied_cells}}` - optional JSON array of `[entity, parameter]` pairs
  already satisfied by comparison shared inputs.
- `{{approved_master_list_source_keys}}` - JSON array of already-approved
  master-list source keys.
- `{{candidate_cap}}` - optional maximum candidate count. Default:
  `schema.defaults.gap_fill_candidate_cap`; if absent, use 5.

Use the schema as the only source of truth for parameter ids, applicability,
`first_class`, `reference_value`, `context_free`, units, and market basis.

If `execution_mode` is `auto`, this is an open-access-only search. Search
specifically for publicly inspectable full text, tables, datasets, repository
copies, government publications, open journals/preprints, and official public
technical material. Do not return a source when only its citation, abstract,
catalog record, or paywalled landing page is visible.

---

## Eligibility

For normal entity coverage:

- Every candidate must cover at least one uncovered parameter where
  `first_class: true` in the schema.
- A candidate may also list non-first-class uncovered parameters when the same
  source is expected to cover them, but a non-first-class parameter alone is not
  enough to spend a candidate slot.
- Do not list parameters outside `{{uncovered_parameters}}`.
- Do not list a cell included in `{{satisfied_cells}}`; shared inputs are
  already authoritative and must not be searched again.
- Do not list any entity other than `{{entity}}`.

For still-missing reference values:

- Use `reference_value_subqueries` for context-free search instructions.
- If a source candidate is expected to cover a reference value directly, put it
  under `"entity": "REF"` with the reference parameter id.
- Do not search or list a `REF` cell included in `{{satisfied_cells}}`.
- Reference-value queries and candidates must not mention the TEA, system,
  product, functional unit, route, or entity names.

Retargeting an already-approved master-list source is allowed only when you are
pointing to a different section/page or a different uncovered parameter. Use a
new `source_key`, set `is_retargeting_of_master_list_source` to `true`, and set
`retargeting_of_source_key` to the original key.

---

## URL Rules

Gap-fill candidates are URL-only:

- `source_url` must be an HTTP(S) source landing page, official PDF,
  institutional repository page, or publisher page.
- Do not output a bare DOI, ISBN, report number, citation-only locator, or
  library-only record.
- Do not use DOI resolver URLs such as `https://doi.org/...`.
- Put a DOI in the optional `doi` field only when you also have a real
  `source_url`.

Avoid textbooks, textbook chapters, reference handbook chapters, encyclopedia
entries, unsourced web pages, blogs, and vendor brochures unless the schema
parameter is specifically an equipment/specification parameter and the vendor is
the dominant primary source.

---

## Output JSON

Return a single JSON object and no prose:

```json
{
  "schema_tea_id": "string copied from tea-schema.json",
  "entity": "{{entity}}",
  "uncovered_parameters_targeted": ["parameter_id"],
  "candidate_cap": 5,
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
      "access_notes": "open access full text verified | publicly accessible official dataset | paywall (human-gated mode only) | other",
      "field_coverage": [
        {
          "entity": "{{entity}}",
          "parameters": ["first_class_uncovered_parameter_id"]
        }
      ],
      "rationale": "1-3 sentences explaining why this fills the gap and what boundary caveats remain",
      "is_retargeting_of_master_list_source": false,
      "retargeting_of_source_key": null
    }
  ],
  "residual_gap_assessment": {
    "parameters_still_uncovered_after_this_round": ["parameter_id"],
    "recommendation": "one sentence recommending another search, analyst estimate, or accepting the gap"
  }
}
```

---

## Constraints

- Emit at most `{{candidate_cap}}` candidates.
- Each normal candidate must cover at least one schema `first_class` parameter
  from `{{uncovered_parameters}}`.
- `field_coverage[].entity` must be `{{entity}}` or `REF`.
- `field_coverage[].parameters` must contain only schema-valid parameter ids for
  that entity.
- Do not duplicate any `{{approved_master_list_source_keys}}` unless retargeting
  with a new key.
- `source_url` must be HTTP(S) and must not be a DOI resolver URL.
- If a parameter cannot be covered by a credible source, leave it out of
  candidates and list it in `residual_gap_assessment`.
- In Auto mode, candidates must be openly accessible without subscription,
  login, purchase, library access, or an access request. If no such evidence is
  found, leave the parameter for transparent estimation rather than citing
  inaccessible evidence.
