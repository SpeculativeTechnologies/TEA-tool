---
name: tea-scope
description: >-
  Step 1 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data). Takes a non-expert from a rough idea
  and any supplied materials to approved starting documents (scope,
  data-requirements, model-requirements) through a relentless, question-driven
  interview. Invoke ONLY when the user runs /tea-scope or explicitly asks to
  start/scope a TEA. Do not self-invoke for general TEA questions.
---

# TEA Scoping (/tea-scope)

Skill 1 of three. You take the user from a rough idea — plus whatever they
supply — to three approved **starting documents**, then hand off to `/tea-model`.
You get there by **asking, not researching**: a relentless, one-question-at-a-time
interview grounded in your own knowledge.

The user understands their technology, decision, and basic TEA terms (CapEx,
OpEx). They do **not** know this tool's schemas, files, stages, or CSVs — keep all
of that invisible. Talk in plain language; do the bookkeeping yourself.

## Invocation

Explicit only. If you were not explicitly invoked, do nothing.

## The deterministic CLI is your source of truth

Never hand-edit `orchestrator-state.json`, `issues.json`, or the user CSVs. Call
`python scripts/orchestrator.py <subcommand>` and read back its JSON. This skill
uses: `init`, `status`, `validate-resume`, `set-stage`, `issue`, `approve`,
`snapshot`, `register-material`, `materialize-user-inputs`.

## Startup routing

Look under `runs/` for existing runs (`validate-resume --run-dir <run>`).

- If a run's `starting_documents` approval is already valid (`status` →
  `approvals.valid`), scoping is **done** — tell the user to run `/tea-model` (or
  `/tea-data` if `model_approved` is also valid). Do not redo scoping.
- If an unfinished run is still in scoping (stage `intake` …
  `starting_documents_review`, not yet approved), summarize it and offer to resume.
- Otherwise start a new run.

Never silently continue a previous session; never adopt a non-orchestrator folder.
See `references/state-and-resume.md`.

## Intake + scoping (the work)

Full contract: `references/intake-and-compatibility.md`. In short:

1. **Init.** Learn the project name + single-vs-comparison, then
   `orchestrator.py init` (for comparisons pass `--option id:Name` per option). Do
   **not** pass `--mode` — the execution mode is chosen later, in `/tea-data`.
2. **Inventory supplied materials.** `register-material` each file/URL; for large
   or independent files fan out read-only `tea-materials-analyst` subagents and
   collect concise summaries. Inspect supplied material **before** asking. Never
   put confidential content in web queries.
3. **Grill the scope.** Resolve ambiguity by **asking, not researching**. Ask
   **one question at a time**, walking each branch of the decision tree and
   resolving dependencies in order. Give the user an up-front estimate of how many
   questions to expect (**~12**), but the governing rule is **ask until the scope
   is unambiguous, not until you hit a number** — if ambiguity remains when you
   reach the estimate, **say so out loud and keep going** (e.g. *"I'd said about a
   dozen, but a few things are still open — let me ask 3–4 more before we lock
   scope."*). Never trim necessary questions to honor the estimate. Give your
   **recommended answer** (and a one-line why) for every question so a non-expert
   can simply confirm or correct. Prefer your own knowledge and the supplied
   materials; if a question can be answered by inspecting a supplied file, do that
   instead of asking. Run a light, targeted web search **only** when genuinely
   stuck on a specific factual point a question cannot resolve — never open-ended
   research. Cover: decision, system/options, boundary, functional unit, basis
   (geography/time/currency), desired outputs, supplied/fixed values,
   entities/parameters, major assumptions, and **which external benchmarks the
   results should later be validated against** (name the metrics only — never fill
   in benchmark values from memory; those are researched in `/tea-data`).
4. **Classify supplied values** (fixed vs candidate) into `user-inputs.csv`.
5. **Understanding check.** Summarize everything; require correction or approval;
   record `intake-summary.md`; `set-stage understanding_review`.

## Starting documents + approval gate

You (not the user) write `scope.md`, `data-requirements.md`, and
`model-requirements.md` (templates in `templates/`). Make `model-requirements.md`
explicit and numeric — it is the specification `/tea-model` implements as a
runnable `model.py`, so spell out every output and its formula and map each
required input to a real schema cell. Three things the docs must contain:

- **Process flow chart (in `scope.md`).** Author a **Mermaid `flowchart`** showing
  each process unit / entity as a node, the flows between them (the "connects to"
  relationships) as edges, and the **key data each unit needs** annotated on its
  node. This gives the user a one-glance picture of what is being modeled. It is
  Mermaid text inside the markdown — diffable and editable, no separate image file.
- **"How the model is solved" walkthrough (in `model-requirements.md`).** A
  plain-language narrative of the solve order (inputs → per-entity calculations →
  aggregation → functional-unit normalization → headline outputs), **followed by a
  concrete worked example of one representative subcomponent** carried end to end.
  Pick the subcomponent that best conveys the overall mechanics. Use a
  **user-supplied fixed value** if one exists; otherwise use round, **clearly
  labeled illustrative numbers** ("illustrative only — real values are gathered in
  the data step"). The goal is to show *how* a number is produced, not to assert
  any value.
- **Benchmarks named, not valued.** Record the validation-target metrics the user
  named (metric + unit), but **do not fill in benchmark values from your own
  knowledge** — `/tea-data` researches them with citations. Each named benchmark
  becomes a cell under the reserved `BENCHMARK` entity at schema-compile time (an
  ordinary, audited cell the model is told to ignore as an input). If the user
  named none, that is fine — no `BENCHMARK` entity is minted.

Compile the schema
(`prompts/stage0-schema-compile.md`; numeric-only — no JSON/TEXT cells), run the
`tea-schema-reviewer` subagent and fix mechanical problems, then present a compact
summary (assumptions, exclusions, input categories, extracted user-value counts,
fixed inputs, links to the docs and `user-inputs.csv`) and require **explicit
approval of all three documents**. **Echo the "how the model is solved" walkthrough
and the worked subcomponent example in the approval message itself** (condensed) —
this is the moment the user decides, so do not make them dig into the doc to
understand how their model will actually be computed. On approval:

```
python scripts/orchestrator.py set-stage --run-dir RUN --stage starting_documents_review
python scripts/orchestrator.py approve --run-dir RUN --type starting_documents \
    --artifact scope.md --artifact data-requirements.md --artifact model-requirements.md
python scripts/orchestrator.py snapshot --run-dir RUN --label starting-documents \
    --artifact scope.md --artifact data-requirements.md --artifact model-requirements.md
```

Then **stop and tell the user to run `/tea-model`.** You do not build the model,
gather data, or pick an execution mode — those belong to the later skills.

## Subagents

Read-only roles in `.claude/agents/tea-*.md`: `tea-materials-analyst` (one per
supplied file/model) and `tea-schema-reviewer` (before the gate). Subagents are
read-only; you serialize all canonical writes through the CLI and phase scripts.
Apply each material's sensitivity policy (`local-only` / `metadata-only` /
`normal-processing`); never include confidential content in web queries. See
`references/interaction-and-gates.md` for the subagent contract.
