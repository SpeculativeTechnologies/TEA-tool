# Estimation Populator

Run once for a single manifest entity. Produce one estimate Audit row for each
blank parameter listed in the manifest, using the single-anchor model:

> **estimate = one real, extracted anchor data point + transparent assumed
> constants + an enabling assumption (the bridge from the anchor's system to this
> cell) + an equation that combines them.**

A backed estimate (`method = single_anchor`, quality tag `E`) is built on exactly
one anchor that was **actually extracted** through the real source pipeline, so it
carries a real `source_key`, `page_ref`, and an A–D extraction `quality_tag`. Only
the bridge and the arithmetic are the estimate layer. When no anchor could be
sourced after the ladder, emit an unbacked estimate (`method = unbacked`, quality
tag `U`) — transparent but explicitly flagged.

## Inputs

Instantiate from `estimation_manifest.json`, the scout result, and the anchor
extraction the orchestrator already ran:

- `{{entity}}`, `{{entity_name}}`, `{{scope_frame}}`
- `{{blank_parameters}}`
- `{{existing_real_extractions}}`
- `{{loop}}`: `1`, `2`, or `3`
- `{{mode}}`: `single_anchor` (loops 1–2) or `unbacked` (loop 3)
- `{{scout_output}}`: chosen analogy + enabling assumption (null for `unbacked`)
- `{{anchor_extraction}}`: the real extractor result for the anchor — its
  `source_key`, `source_url`, `page_ref`, extracted `value`/`units`, and the A–D
  `quality_tag` the extraction earned (null for `unbacked`)
- `{{functional_unit}}`, `{{basis}}`, `{{execution_mode}}`

## Rules

- Emit rows using `entity` and `parameter`; exactly one row per
  `blank_parameters[]` item; never a row for an `existing_real_extractions` cell.
- Every row carries a numeric value (compute it from the anchor and the assumed
  constants). There are **no blank rows** — loop 3 still produces a value.
- `single_anchor` rows: `quality_tag = "E"`, `method = single_anchor`. The
  `anchor` must be the real extracted anchor (`source_key`, `page_ref`, A–D
  `quality_tag` — never `E`/`U` and never blank). The row's `source_key` is the
  anchor's `source_key`. Use **exactly one** searched anchor; everything else in
  the equation is an `assumed_constants[]` entry (a stoichiometric ratio, a
  scaling exponent, a textbook constant) with a stated basis — not a second
  search.
- Name the `enabling_assumption` in one plain sentence: why the anchor's system is
  similar enough to this cell (e.g. "double-melting metal Y is energetically
  similar enough to metal X for this estimate"). Show the `equation` and the
  `derivation_steps`.
- `unbacked` rows (loop 3 only): `quality_tag = "U"`, `method = unbacked`,
  `unbacked = true`, no `anchor`, no cited source. Still give the enabling
  assumption, equation, derivation, a numeric value, low confidence, and clear
  caveats.
- In Auto mode, the anchor evidence must be openly inspectable; include
  `access_notes` on the anchor confirming open/public full-text access.

## Output

Return one JSON object and no prose:

```json
{
  "entity": "{{entity}}",
  "mode_used": "single_anchor",
  "rows": [
    {
      "entity": "{{entity}}",
      "parameter": "specific_capex",
      "source_key": "metal-y-doublemelt-capex",
      "source_url": "https://example.com/metal-y",
      "page_ref": "Table 4, p. 18",
      "raw_value": "1320",
      "raw_units": "USD/kg",
      "raw_basis_year": "2024",
      "quality_tag": "E",
      "relevance_status": "clear",
      "extractor_notes": "Single-anchor estimate; see estimate_justification.",
      "estimate_justification": {
        "method": "single_anchor",
        "loop": 1,
        "enabling_assumption": "Double-melting of metal Y is energetically similar enough to metal X for a CAPEX estimate.",
        "equation": "specific_capex_X = anchor_capex_Y * (scale_Y / scale_X) ** 0.6",
        "anchor": {
          "source_key": "metal-y-doublemelt-capex",
          "source_url": "https://example.com/metal-y",
          "title": "Metal Y double-melt cost study",
          "page_ref": "Table 4, p. 18",
          "value": "1100",
          "units": "USD/kg",
          "quality_tag": "B",
          "access_notes": "open access full text verified"
        },
        "assumed_constants": [
          {"symbol": "scaling_exponent", "value": "0.6", "units": "", "basis": "Williams six-tenths rule"},
          {"symbol": "scale_ratio", "value": "1.2", "units": "", "basis": "relative plant scale"}
        ],
        "derivation_steps": [
          "Read anchor_capex_Y = 1100 USD/kg from metal-y-doublemelt-capex Table 4.",
          "Apply six-tenths scaling with scale_ratio 1.2: 1100 * 1.2**0.6 = 1320.",
          "Final: specific_capex_X = 1320 USD/kg."
        ],
        "estimator_confidence": "medium",
        "caveats": ["Bridges from metal Y; verify the melting-energy analogy."]
      }
    }
  ]
}
```

Unbacked (loop 3) rows use this shape:

```json
{
  "entity": "{{entity}}",
  "parameter": "specific_capex",
  "source_key": "",
  "source_url": "",
  "page_ref": "n/a (unbacked estimate)",
  "raw_value": "1500",
  "raw_units": "USD/kg",
  "raw_basis_year": "2025",
  "quality_tag": "U",
  "relevance_status": "clear",
  "estimate_justification": {
    "method": "unbacked",
    "loop": 3,
    "unbacked": true,
    "enabling_assumption": "No sourceable anchor exists for any close analogue; transparent engineering judgment only.",
    "equation": "specific_capex ~= typical specialty-metal melt CAPEX",
    "derivation_steps": [
      "Loops 1-2 found no openly sourceable anchor.",
      "Assume a mid-range specialty-metal value: 1500 USD/kg."
    ],
    "estimator_confidence": "low",
    "caveats": ["Unbacked estimate — shore this up before relying on the result."]
  }
}
```

## Self-Check

- One row per blank parameter, no duplicates.
- `single_anchor` rows: `quality_tag` `E`; `anchor` has a kebab-case
  `source_key`, an HTTP(S) `source_url`, a `page_ref`, and an A–D `quality_tag`;
  the row's `source_key` equals the anchor's; at most one searched anchor.
- `unbacked` rows: `quality_tag` `U`, `loop` 3, `unbacked` true, no anchor.
- Every row has `enabling_assumption`, `equation`, `derivation_steps`, and a
  numeric value.
- In Auto mode, the anchor carries `access_notes` confirming open access.
- Numeric values obey basic bounds: fractions in [0, 1], nonnegative
  monetary/intensity/rate values, positive CAPEX.
