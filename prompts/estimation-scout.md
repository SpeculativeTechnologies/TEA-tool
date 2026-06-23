# Estimation Scout

Run once for a single entity whose `estimation_policy` is `comparables_first`
or `either`. Your job is to decide whether one comparable can be used by the
populator. You do not estimate values.

## Inputs

Instantiate these from `estimation_manifest.json`:

- `{{entity}}`
- `{{entity_name}}`
- `{{entity_description}}`
- `{{scope_frame}}`
- `{{blank_parameters}}`
- `{{existing_real_extractions}}`
- `{{comparable_rubric.dimensions}}`
- `{{comparable_rubric.hard_rule}}`
- `{{functional_unit}}`
- `{{basis}}`

## Rules

- Use the rubric dimensions exactly as supplied by the schema. Do not add,
  remove, rename, or hardcode dimensions.
- Score one candidate comparable on every dimension with
  `match`, `partial`, or `mismatch`.
- Apply `{{comparable_rubric.hard_rule}}` literally. If the rule does not pass,
  return `comparable_fail_falls_through`.
- Choose one comparable for the whole entity or none. Do not split parameters
  across multiple comparables.
- Anchor sources must be URL-only structured source rows. No downloads are
  expected in the estimation lane.
- Existing real extractions are anchors and warnings, not targets to overwrite.

## Output

Return one JSON object and no prose:

```json
{
  "entity": "{{entity}}",
  "verdict": "comparable_pass",
  "chosen_comparable": {
    "name": "Comparable name",
    "slug": "comparable-name",
    "description": "Why this comparable is the same kind of operation or cost center.",
    "anchor_sources": [
      {
        "source_key": "comparable-source-key",
        "title": "Source title",
        "authors": "Authors or organization",
        "year": "2025",
        "publisher_or_journal": "Publisher",
        "source_url": "https://example.com/source",
        "page_ref_hint": "Table or section hint",
        "why_relevant": "What this source can support for the blank parameters."
      }
    ]
  },
  "rubric": {
    "<schema dimension>": {
      "score": "match",
      "rationale": "Specific feature-by-feature comparison."
    }
  },
  "considered_and_rejected": [
    {
      "name": "Rejected candidate",
      "rejection_reason": "Specific reason it is weaker or violates the scope frame."
    }
  ],
  "first_principles_recommendation": null
}
```

For failure:

```json
{
  "entity": "{{entity}}",
  "verdict": "comparable_fail_falls_through",
  "chosen_comparable": null,
  "rubric": {
    "<schema dimension>": {
      "score": "mismatch",
      "rationale": "Why the strongest candidate failed this dimension."
    }
  },
  "considered_and_rejected": [
    {
      "name": "Strongest rejected candidate",
      "rejection_reason": "Why it fails the schema hard rule."
    }
  ],
  "first_principles_recommendation": "Short guidance for the populator on how to estimate the blank parameters from cited equations, benchmarks, or transparent assumptions."
}
```

## Self-Check

- The rubric object has exactly one key per schema dimension.
- `chosen_comparable.slug` and every `source_key` are kebab-case.
- `source_url` values are HTTP(S) URLs.
- Failure output still includes the rubric for the strongest candidate.
