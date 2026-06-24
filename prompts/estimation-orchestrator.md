# Estimation Orchestrator

Phase 6.1 fills currently blank schema cells with E-quality estimates. You are
the wiring layer: read `estimation_manifest.json`, route each entity by its
`estimation_policy`, run the scout/populator agents, mechanically validate
their JSON, then call `scripts/append_estimation_rows.py`.

Do not invent values in this prompt. Do not judge plausibility beyond mechanical
schema checks. Every emitted row is reviewed later through
`held_estimates.csv`; in Auto mode, the Auto Gate Agent performs that review
immediately.

## Inputs

- `tea-schema.json`, already compiled and validated.
- `estimation_manifest.json`, produced by:

```bash
python scripts/build_estimation_manifest.py --schema tea-schema.json --audit Audit_normalized_consolidated.csv --main-input "Main Input.csv"
```

The manifest carries:

- `schema_tea_id`, `execution_mode`, `functional_unit`, `basis`, and
  `quality_tags`.
- `comparable_rubric.dimensions` and `comparable_rubric.hard_rule` from the
  schema. These are the only rubric fields the scout may score.
- `entities[]`, each with `entity`, `entity_name`, `scope_frame`,
  `estimation_policy`, `blank_parameters[]`, and `existing_real_extractions[]`.

## Routing

For each manifest entity:

- `comparables_first`: run `estimation-scout.md`; if the scout returns
  `comparable_pass`, run the populator in `comparable` mode. If the scout
  returns `comparable_fail_falls_through`, run the populator in
  `first_principles` mode.
- `either`: run the scout first, then route exactly as above.
- `first_principles_only`: skip scout and run the populator in
  `first_principles` mode.

For the reserved `REF` entity, use `first_principles` mode and require
context-free reference-value citations.

## Scout Validation

Scout output must be a single JSON object:

```json
{
  "entity": "entity_id",
  "verdict": "comparable_pass",
  "chosen_comparable": {
    "name": "...",
    "slug": "kebab-case",
    "description": "...",
    "anchor_sources": [
      {
        "source_key": "kebab-case",
        "title": "...",
        "source_url": "https://...",
        "page_ref_hint": "...",
        "why_relevant": "..."
      }
    ]
  },
  "rubric": {
    "<dimension from manifest.comparable_rubric.dimensions>": {
      "score": "match",
      "rationale": "Specific comparison."
    }
  },
  "considered_and_rejected": [
    {"name": "...", "rejection_reason": "..."}
  ],
  "first_principles_recommendation": null
}
```

Mechanical checks:

- `verdict` is `comparable_pass` or `comparable_fail_falls_through`.
- Rubric keys exactly cover the manifest rubric dimensions.
- Scores are `match`, `partial`, or `mismatch`.
- If `comparable_pass`, `chosen_comparable` and at least one anchor source are
  required.
- If `comparable_fail_falls_through`, `chosen_comparable` is null and
  `first_principles_recommendation` is non-empty.

If a scout fails validation, re-prompt once with the validation error. If it
fails again, override the verdict to `comparable_fail_falls_through`.

## Populator Validation

Populator output must be a single JSON object:

```json
{
  "entity": "entity_id",
  "mode_used": "first_principles",
  "rows": [
    {
      "entity": "entity_id",
      "parameter": "parameter_id",
      "source_key": "registered-source-key",
      "source_url": "https://...",
      "page_ref": "n/a (estimate) or citation page",
      "raw_value": "100",
      "raw_units": "USD/month",
      "raw_basis_year": "2025",
      "quality_tag": "E",
      "relevance_status": "clear",
      "cited_sources": [
        {
          "source_key": "registered-source-key",
          "title": "...",
          "authors": "...",
          "year": "2025",
          "publisher_or_journal": "...",
          "source_url": "https://...",
          "page_or_table_reference": "..."
        }
      ],
      "estimate_justification": {
        "method": "first_principles",
        "cited_source_keys": ["registered-source-key"],
        "comparable": null,
        "first_principles": {
          "method_name": "...",
          "equations": ["..."],
          "parameters": [
            {"symbol": "...", "value": "...", "units": "...", "source_key": "registered-source-key"}
          ],
          "derivation_steps": ["..."]
        },
        "estimator_confidence": "low|medium|high",
        "caveats": []
      }
    }
  ]
}
```

Mechanical checks:

- Exactly one row per `blank_parameters[]` item.
- Every row uses `entity` and `parameter`, not domain-specific vocabulary.
- `quality_tag` is `E`.
- Non-failed rows include structured `cited_sources`; the row `source_key` is
  one of those cited source keys and has an HTTP(S) URL.
- `method` is `comparable`, `first_principles`, or `failed`.
- `comparable` rows include the schema rubric dimensions and leave
  `first_principles` null.
- `first_principles` rows include equations, parameters with sources, and
  derivation steps.
- In Auto with Human Gates mode, `failed` rows leave value fields blank and
  include `failure_reason`.
- In Auto mode, `failed` is forbidden. Make a best-effort, single numeric
  estimate for every blank cell and clearly label assumptions and confidence.

If a populator fails validation, re-prompt once. In Auto with Human Gates mode,
a second failure may produce failed rows. In Auto mode, retry with a simpler
first-principles or conservative comparable estimate; do not emit a blank cell.

## Write

Aggregate all validated rows:

```json
{
  "schema_tea_id": "<manifest schema_tea_id>",
  "generated_at_iso": "<manifest generated_at_iso>",
  "force_refresh": false,
  "rows": []
}
```

Write `estimation_output.json`, then run:

```bash
python scripts/append_estimation_rows.py --schema tea-schema.json --input estimation_output.json --audit Audit.csv --sources Sources.csv
```

If the manifest was built with `force_refresh: true`, include
`--force-refresh`.

## Report

Print a compact report with entities processed, scout verdicts, rows emitted by
method, failed cells, low-confidence rows, and the next command:

```bash
python scripts/sweep_held_estimates.py --audit Audit.csv --output held_estimates.csv --sources Sources.csv
```
