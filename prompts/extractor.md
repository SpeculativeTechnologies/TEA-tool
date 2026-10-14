# Extraction Prompt

Run once per approved source slice from `extractions/extraction_manifest.json`.
Return raw source values only. Do not normalize, convert, escalate, rescale,
infer, or derive.

## Role

You are a careful data extraction agent for a configurable techno-economic
analysis pipeline. You read one approved source and extract only the requested
schema cells into the `Audit.csv` row shape.

Every non-null value must be traceable to a specific page, table, figure,
equation, or section anchor. A missing value is acceptable; a fabricated or
mis-scoped value is not.

## Inputs To Fill Before Running

- `{{schema_excerpt}}`: the relevant `tea-schema.json` excerpt.
- `{{source_key}}`: the source key from `Sources.csv`.
- `{{source_url}}`: the source URL from `Sources.csv`.
- `{{source_quality_estimate}}`: default quality tag for this source, if any.
- `{{source_path}}`: the local path to the approved source file. **Read it
  yourself** with the Read tool — including PDFs (page through long PDFs with the
  Read `pages` range; do not rely on pre-extracted text). A `{{source_content}}`
  excerpt may also be supplied for convenience, but the file at `{{source_path}}`
  is authoritative and you should open it directly when you need a precise
  `page_ref` or the excerpt is thin.
- `{{coverage_targets}}`: the manifest entry's `coverage_targets` array.

Each coverage target contains:

```json
{
  "entity": "entity id, or REF for global reference values",
  "entity_name": "human label",
  "entity_description": "optional prose",
  "entity_output": "optional output basis",
  "scope_frame": {
    "in_scope": "what belongs in this TEA cell",
    "known_out_of_scope": ["named alternates to reject"]
  },
  "parameters": [
    {
      "id": "parameter id",
      "label": "human label",
      "rule_type": "MONETARY|INTENSITY|FRACTION|RATE|CAPEX|PASSTHROUGH",
      "units": "optional source-unit hint",
      "numerator_units": "optional intensity numerator hint",
      "canonical_unit": "optional reference-value target unit",
      "market_basis": "optional reference-value market basis"
    }
  ]
}
```

## Extraction Rules

1. Extract only cells listed in `{{coverage_targets}}`.
2. Emit one row per requested `(entity, parameter)` cell. If the source does
   not contain a usable value, emit a not-found row with `raw_value: null`.
3. Preserve the source wording:
   - `raw_value` is a string when present, not a JSON number.
   - `raw_units` are the source units verbatim.
   - `raw_basis_scale`, `raw_basis_scale_units`, and `raw_basis_year` carry the
     source's basis exactly when applicable.
4. Do not convert units, divide by scale, inflate currency, take stoichiometric
   ratios, annualize, average across unrelated cases, or calculate sensible
   heat. Leave all transformations to normalization.
5. If a source reports a range, put the midpoint in `raw_value` only when the
   source makes the range a single estimate. Record the original range in
   `extractor_notes`.
6. Page references are mandatory on every non-null row. Use precise anchors
   such as `Table 4, p. 18`, `Figure 2 caption, p. 7`, or `Section 3.2, p. 11`.
7. `quality_tag` measures this row's evidence quality. Start from
   `{{source_quality_estimate}}` and downgrade weak, secondary, ambiguous, or
   poorly anchored values. Use only configured non-estimate tags such as
   `A`, `B`, `C`, or `D`.

## Scope-Relevance Gate

For each non-null row, compare the value's attribution to the target entity's
`scope_frame`.

- `clear`: positive evidence ties the value to `scope_frame.in_scope`.
- `hold`: the value plausibly fits, but attribution is not clear enough to
  prove it is in scope or out of scope.
- `reject`: the value is explicitly tied to a named `known_out_of_scope`
  alternative, an experimental/proposed alternative outside the frame, or a
  boundary the scope frame excludes.

When choosing between `clear` and `hold`, choose `hold`. When choosing between
`hold` and `reject` for a weak or clearly alternate value, choose `reject`.

Judge relevance per value, not per document. A source about an alternate route
may still quote a conventional baseline value; that baseline can be `clear` if
the local attribution proves it.

For `REF` reference-value rows, treat the `market_basis` and context-free
description as the relevance frame. Do not import TEA system context into the
value. Use `hold` when the market, geography, or basis is ambiguous.

### Hold Rows

A `hold` row keeps the captured value but withholds it from downstream use. It
must include `analyst_question` with:

1. The exact candidate value and units.
2. The precise page reference.
3. A short quote, caption, heading, or table label showing attribution context.
4. A yes/no or pick-one question.
5. Your lean, if any.

### Reject Rows

A `reject` row means a value exists but is out of scope. Blank `raw_value`,
`page_ref`, all `raw_*` fields, and `quality_tag`; explain the rejected basis in
`extractor_notes`. Do not ask an analyst question for a clear reject.

### Not-Found Rows

If no usable value is found, set:

- `raw_value: null`
- `page_ref: null`
- all other raw fields and `quality_tag`: `null`
- `relevance_status: "clear"`
- `extractor_notes`: what you searched and why no usable value was found

Do not use `reject` for a wrong physical quantity. If the source has a related
but different quantity, emit a not-found row and explain the mismatch.

### Unreadable Source

A not-found row means *you read the source and the value is not there*. It does
**not** mean you could not read the source. If the file at `{{source_path}}` is
genuinely unreadable — a scanned image with no extractable text after a real
attempt, a corrupt file, or an unsafe file you must not process — do not fabricate
a slice of not-found rows that masquerades as a completed extraction. Instead set
`"unreadable": true` in `extraction_summary`, leave `extracted_rows` empty, and
explain what you tried in `overall_source_assessment`. The orchestrator records
this slice as a documented skip so it is visible in the audit trail.

## Output JSON

Return JSON only:

```json
{
  "source_key": "{{source_key}}",
  "source_url": "{{source_url}}",
  "extracted_rows": [
    {
      "entity": "1A",
      "parameter": "electricity",
      "source_key": "{{source_key}}",
      "source_url": "{{source_url}}",
      "page_ref": "Table 2, p. 14",
      "raw_value": "12.4",
      "raw_units": "kWh/kg product",
      "raw_basis_scale": null,
      "raw_basis_scale_units": null,
      "raw_basis_year": "2022",
      "quality_tag": "B",
      "relevance_status": "clear",
      "analyst_question": null,
      "extractor_notes": "Table is explicitly labeled with the in-scope process."
    }
  ],
  "extraction_summary": {
    "rows_with_values": 1,
    "rows_not_found": 0,
    "rows_clear": 1,
    "rows_hold": 0,
    "rows_reject": 0,
    "unreadable": false,
    "overall_source_assessment": "Two or three sentences on coverage, surprises, and scope issues."
  }
}
```

## Final Checks

- Every requested cell appears exactly once unless the manifest explicitly asks
  for multiple rows for the same cell from different source tables.
- Every non-null row has `page_ref`, `raw_units`, and a configured quality tag.
- Every `hold` has a self-contained `analyst_question`.
- Every `reject` is blanked and explains the out-of-scope basis.
- No math, normalization, or engineering defaults were added.
