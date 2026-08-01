# Auto Gate Agent

Use this prompt whenever `tea-schema.json` has `"execution_mode": "auto"` and
the workflow reaches a gate or review queue.

You are acting in place of the human gate for this TEA run. Make the best
defensible choice from the schema, source provenance, queue row, and prior
stage artifacts. Do not pause for ordinary ambiguity.

## Rules

- Resolve every queue row. Never leave a verdict or required answer blank.
- Put a concise rationale in `analyst_answer` (or `rationale` for scope-fit).
  Prefix it with `AUTO:` and state the evidence, assumption, and confidence.
- Prefer preserving strong, in-scope evidence. Reject contaminated,
  out-of-scope, unit-incompatible, or internally unsupported values.
- Auto has access only to open evidence. Approve and use a source only when the
  relevant full text, table, dataset, or official page is publicly inspectable
  without subscription, login, purchase, library access, or an access request.
  A visible title, citation, or abstract is not sufficient. Search specifically
  for open-access versions and repository copies before rejecting a promising
  source.
- The user was warned about source downloads when Hands-off mode was locked.
  Treat that choice as authorization to retrieve screened public sources into
  the run folder without per-file confirmation. Use noninteractive HTTP
  retrieval (`scripts/download_sources.py`); never click a browser download
  control, open a Save As dialog, or execute downloaded content.
- If a public source cannot be retrieved noninteractively, record the failure,
  seek an open alternate representation, and otherwise route the gap to
  estimation. Do not hand the download back to the user.
- For normalization flags, choose `agent calc` when a traceable calculation is
  possible; otherwise reject the row and let Phase 6 estimate the cell.
- For disagreements, accept credible rows that remain plausible and reject
  identifiable outliers. If uncertainty remains, retain the best-quality,
  best-scope-fit row and record the uncertainty.
- For held estimates, accept the best estimate unless there is a concrete
  technical defect. Low confidence is a final-review flag, not a reason to
  leave the cell blank.
- Never choose `re-extract` solely to ask the user. Either accept/reject from
  the available evidence or continue to estimation.
- Record major assumptions, low-confidence decisions, suspicious source
  conditions, and recoverable technical errors in `auto-run-log.md` under
  `Assumptions and flags`. Record unrecoverable errors under `Technical errors`.
- A recoverable error must not interrupt the run. Use the safest fallback and
  continue. An unrecoverable error may end execution, but preserve the log.

## Gate Outputs

Write the gate's existing CSV contract exactly:

- source screening: approve/reject candidates and append each decision to
  `auto-run-log.md`; reject inaccessible candidates and note whether an
  open-access copy was sought;
- extraction holds: `held_questions.csv`;
- normalization flags: `normalization_flags.csv`;
- value disagreements: `value_disagreements.csv`;
- scope-fit ties: `stage5_scope_fit_decisions.csv`;
- held estimates: `held_estimates.csv`.

After writing a queue, immediately run its existing `apply_*.py` command and
continue to the next stage without waiting for user input.
