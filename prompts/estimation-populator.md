# Estimation Populator

Run once for a single manifest entity. Produce one E-quality Audit row for each
blank parameter listed in the manifest. Every non-failed row must cite
structured URL-only sources so `scripts/append_estimation_rows.py` can register
them in `Sources.csv` with `source_role=estimate`.

## Inputs

Instantiate from `estimation_manifest.json` and the scout result:

- `{{entity}}`
- `{{entity_name}}`
- `{{scope_frame}}`
- `{{estimation_policy}}`
- `{{blank_parameters}}`
- `{{existing_real_extractions}}`
- `{{mode}}`: `comparable` or `first_principles`
- `{{scout_output}}`: null for `first_principles_only`
- `{{functional_unit}}`
- `{{basis}}`
- `{{comparable_rubric}}`

## Rules

- Emit rows using `entity` and `parameter`.
- Emit exactly one row for each `blank_parameters[]` item.
- Do not emit a row for anything already present in
  `existing_real_extractions`.
- Use `quality_tag: "E"` and `relevance_status: "clear"`.
- Do not use unsourced intuition. Each non-failed row needs a
  `cited_sources[]` array, and the row's `source_key` must be one of those
  cited source keys.
- For comparable mode, repeat the scout comparable and rubric in
  `estimate_justification.comparable`; do not rescore it.
- For first-principles mode, show equations, sourced parameters, and derivation
  steps. Any cited parameter should reference a `source_key` from
  `cited_sources[]`.
- If a value cannot be grounded, emit a failed row with blank value fields and
  a `failure_reason`; this is better than a weak number.

## Output

Return one JSON object and no prose:

```json
{
  "entity": "{{entity}}",
  "mode_used": "first_principles",
  "rows": [
    {
      "entity": "{{entity}}",
      "parameter": "monthly_cost",
      "source_key": "benchmark-source-key",
      "source_url": "https://example.com/benchmark",
      "page_ref": "Table 2",
      "raw_value": "100",
      "raw_units": "USD/month",
      "raw_basis_scale": null,
      "raw_basis_scale_units": null,
      "raw_basis_year": "2025",
      "normalized_value": null,
      "normalized_units": null,
      "quality_tag": "E",
      "relevance_status": "clear",
      "extractor_notes": "Estimate; see estimate_justification.",
      "cited_sources": [
        {
          "source_key": "benchmark-source-key",
          "title": "Benchmark source title",
          "authors": "Author or organization",
          "year": "2025",
          "publisher_or_journal": "Publisher",
          "source_url": "https://example.com/benchmark",
          "page_or_table_reference": "Table 2",
          "notes": "Used for monthly benchmark."
        }
      ],
      "estimate_justification": {
        "method": "first_principles",
        "cited_source_keys": ["benchmark-source-key"],
        "comparable": null,
        "first_principles": {
          "method_name": "Transparent estimate name",
          "equations": ["monthly_cost = unit_price * units_per_month"],
          "parameters": [
            {
              "symbol": "unit_price",
              "value": "100",
              "units": "USD/month",
              "source_key": "benchmark-source-key"
            }
          ],
          "derivation_steps": [
            "Step 1: read unit_price from benchmark-source-key Table 2.",
            "Final: monthly_cost = 100 USD/month."
          ]
        },
        "estimator_confidence": "low",
        "caveats": ["State the main uncertainty."]
      }
    }
  ]
}
```

Comparable-mode rows use this justification shape:

```json
{
  "method": "comparable",
  "cited_source_keys": ["comparable-source-key"],
  "comparable": {
    "process_name": "Comparable name",
    "slug": "comparable-name",
    "rubric": {
      "<schema dimension>": {"score": "match", "rationale": "Scout rationale."}
    },
    "sources": [
      {
        "source_key": "comparable-source-key",
        "title": "Source title",
        "source_url": "https://example.com/source",
        "page_ref": "Table 4",
        "extracted_value": "Value used for this row."
      }
    ]
  },
  "first_principles": null,
  "estimator_confidence": "medium",
  "caveats": []
}
```

Failed rows use:

```json
{
  "entity": "{{entity}}",
  "parameter": "specific_capex",
  "source_key": null,
  "source_url": null,
  "page_ref": "n/a (failed estimate)",
  "raw_value": null,
  "raw_units": null,
  "normalized_value": null,
  "normalized_units": null,
  "quality_tag": "E",
  "relevance_status": "clear",
  "estimate_justification": {
    "method": "failed",
    "cited_source_keys": [],
    "comparable": null,
    "first_principles": null,
    "estimator_confidence": "low",
    "caveats": ["Why no grounded estimate was possible."],
    "failure_reason": "No grounded estimate available."
  }
}
```

## Self-Check

- One row per blank parameter, no duplicates.
- Every non-failed row has `cited_sources[]` with kebab-case `source_key` and
  HTTP(S) `source_url`.
- The row `source_key` appears in `cited_sources[]`.
- Numeric values already normalized by you obey basic bounds when present:
  fractions in [0, 1], nonnegative monetary/intensity/rate values, and positive
  `capex_usd` for CAPEX rows.
