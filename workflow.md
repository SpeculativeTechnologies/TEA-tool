# General TEA Workflow

This file is a growing execution guide. T3 contributes the search-lane gates and
commands; T9 will expand the full end-to-end analyst guide.

---

## Phase 1 - Master-list Search

Run `prompts/master-list-search.md` with the current `tea-schema.json`. The
agent returns candidate JSON only.

### 1.2 Screen + Download Gate

Review each candidate before downloading:

- Is the source real and locatable from `source_url`?
- Does the expected `field_coverage` use only valid schema entity/parameter
  pairs?
- Is the source boundary plausibly inside the covered entity scope frame?
- Is the quality estimate credible?
- For `REF` reference values, is the search/candidate context-free, with no TEA
  system or entity context?

Download only approved sources into `master list sources/`. Do not register
undownloaded candidates.

### 1.3 Normalize Filenames

Dry-run first:

```powershell
python scripts/rename_sources.py --schema tea-schema.json --input master-list.json --source-dir "master list sources"
```

After reviewing matches:

```powershell
python scripts/rename_sources.py --schema tea-schema.json --input master-list.json --source-dir "master list sources" --apply
```

The normalized filename form is `{entity_or_chain}_{source_key}.{ext}`.

### 1.4 Register Sources

```powershell
python scripts/register_sources.py --schema tea-schema.json --input master-list.json --source-dir "master list sources" --sources Sources.csv
```

Only candidates with a matching source file are appended to `Sources.csv`.
Rows are written with `source_role=extraction` and `source_url`.

---

## Phase 2 - Gap-fill Search

Run `prompts/gap-fill-search.md` once per entity with uncovered parameters.
Use `schema.defaults.gap_fill_candidate_cap` when present, otherwise 5.

### 2.2 Screen + Download Gate

Review each gap-fill candidate before downloading:

- Does it cover at least one uncovered schema `first_class` parameter for the
  target entity?
- Is `source_url` a real HTTP(S) source page, not a DOI-only locator or DOI
  resolver URL?
- Is it non-duplicative versus approved master-list sources, or explicitly
  retargeted with a new `source_key`?
- Does `field_coverage` list only the target entity or `REF`?
- Are residual gaps documented instead of filled with weak guesses?

Download approved sources into `gap fill sources/`.

### 2.3 Normalize Filenames

```powershell
python scripts/rename_sources.py --schema tea-schema.json --input gap-fill-ENTITY.json --source-dir "gap fill sources" --mode gap --entity ENTITY --uncovered-parameters parameter_a,parameter_b
```

Add `--apply` only after the dry-run matches are reviewed.

### 2.4 Register Sources

```powershell
python scripts/register_sources.py --schema tea-schema.json --input gap-fill-ENTITY.json --source-dir "gap fill sources" --sources Sources.csv --mode gap --entity ENTITY --uncovered-parameters parameter_a,parameter_b
```

Candidate JSON remains the search history. `Sources.csv` is the accepted-source
registry.

---

## Phase 3 - Extraction

Build the extraction manifest from the accepted search JSON plus registered
sources:

```powershell
python scripts/extraction_manifest.py --schema tea-schema.json --input master-list.json --input gap-fill-ENTITY.json --source-dir "master list sources" --source-dir "gap fill sources" --sources Sources.csv --output extractions/extraction_manifest.json
```

The manifest writes one slice per registered, downloaded source. Coverage comes
from candidate `field_coverage`; source locators come from `Sources.csv`.

### 3.1 Run Extractor Batches

Get the next resumable batch:

```powershell
python scripts/next_batch.py --manifest extractions/extraction_manifest.json
```

Run `prompts/extractor.md` once per slice, using the slice's
`coverage_targets`, `source_key`, `source_url`, quality estimate, source file
content, and entity `scope_frame`. Save each JSON to the slice's `output_json`.

### 3.2 Ingest Extractor Output

```powershell
python scripts/ingest_extractor_output.py --schema tea-schema.json --input extractions/SOURCE.extraction.json --audit Audit.csv --sources Sources.csv --manifest extractions/extraction_manifest.json
```

Ingest validates entity/parameter applicability, requires `page_ref` for
value-bearing rows, and denormalizes `source_url` from `Sources.csv`.

### 3.3 Resolve Scope Holds

Sweep unresolved `hold` rows:

```powershell
python scripts/sweep_held_questions.py --audit Audit.csv --output held_questions.csv
```

Fill `proposed_verdict` with `accept`, `reject`, or `re-extract`, plus
`analyst_answer`. Then apply:

```powershell
python scripts/apply_held_verdicts.py --audit Audit.csv --queue held_questions.csv
```

Normalization must hard-block while any `Audit.csv` row still has
`relevance_status=hold`.
