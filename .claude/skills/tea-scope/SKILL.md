---
name: tea-scope
description: >-
  Step 1 of the explicitly-invoked TEA orchestrator, run in series
  (/tea-scope -> /tea-model -> /tea-data -> /tea-insights). Takes a non-expert
  from a rough idea
  and any supplied materials to approved starting documents (scope,
  data-requirements, model-requirements) through a relentless, question-driven
  interview. Invoke ONLY when the user runs /tea-scope or explicitly asks to
  start/scope a TEA. Do not self-invoke for general TEA questions.
---

# TEA Scoping (/tea-scope)

Skill 1 of four. You take the user from a rough idea — plus whatever they
supply — to the approved **starting documents**, then hand off to `/tea-model`.
You get there by **asking, not researching**: a relentless, one-question-at-a-time
interview grounded in your own knowledge.

The user understands their technology, decision, and basic TEA terms (CapEx,
OpEx). They do **not** know this tool's schemas, files, stages, or CSVs — keep all
of that invisible. Talk in plain language; do the bookkeeping yourself.

**What a TEA is (the model you are scoping).** A TEA is **one or more connected unit
processes — "entities" — each with inputs, outputs, and optionally waste streams.**
The entities wired together are the system; the cost flows along that chain to the
headline number. A simple system may be a **single entity**, and that is fine. An
entity can be one process step *or* a phase that bundles many unit operations — pick
the granularity that matches the decision and the data that can be gotten. The
**parameters** are the variables each entity needs (a price, a yield, an energy
intensity, a CapEx). Make this structure visible to the user throughout: the
interview, the scope doc, and the diagram all describe the same connected entities.

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
   **Walk the entities explicitly.** Decompose the system into its connected
   entities, then for **each entity** confirm with the user: what flows **in**
   (feedstocks, energy, services), what flows **out** (the product/intermediate it
   hands downstream), any **waste streams** (and whether they carry a disposal
   cost), what it **connects to**, and the **key parameters** it needs. A
   single-entity system is fine — still walk its inputs/outputs/parameters. This is
   what lets a non-expert see *what each unit contributes* before approving.
4. **Classify supplied values** (fixed vs candidate) into `user-inputs.csv`.
5. **Understanding check.** Summarize everything; require correction or approval;
   record `intake-summary.md`; `set-stage understanding_review`.

## Starting documents + approval gate

You (not the user) write `scope.md`, `process-flow.md`, `data-requirements.md`, and
`model-requirements.md` (templates in `templates/`). Make `model-requirements.md`
explicit and numeric — it is the specification `/tea-model` implements as a
runnable `model.py`, so spell out every output and its formula and map each
required input to a real schema cell. Three things the docs must contain:

- **Process flow diagram (its own `process-flow.md`).** Author a **Mermaid
  `flowchart`** from the entity decomposition: each entity is a node, each "connects
  to" relationship is an edge. Each node describes how that unit **operates** —
  annotate it with everything that flows **in** (feedstocks, energy, consumables,
  labor — the operating-cost drivers), what flows **out** (the product/intermediate
  handed downstream), and any **waste stream** (with disposal cost if it carries
  one). Show energy and other operating inputs **on the node that consumes them**.
  **No data/parameter nodes, and no `REF` or `BENCHMARK` nodes** — the flowchart is
  physical operation only; benchmarks live in scope.md, not here, and CapEx is a
  property of the unit, not a flow, so leave it off. This is the one-glance picture
  of how the system runs. It lives in its **own `process-flow.md`** (not buried in
  scope.md), linked from scope.md §6, and is approved and snapshotted alongside the
  other docs.
- **"How the model is solved" walkthrough (in `model-requirements.md`).** A
  plain-language narrative that **walks the actual entity graph**: inputs → each
  entity's contribution → aggregation across the connected entities →
  functional-unit normalization → the headline number (e.g. $/kg, $/area). Tie it to
  the process-flow diagram so the words and the picture line up. **Then carry one
  representative input all the way through to the headline** — through its entity,
  then aggregation and normalization — so the reader sees the *whole chain* to the
  final per-functional-unit figure, not an isolated line item. Use a
  **user-supplied fixed value** if one exists; otherwise round, **clearly labeled
  illustrative numbers** ("illustrative only — real values are gathered in the data
  step"). The goal is to show *how* the headline number is produced, not to assert
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
fixed inputs, **the process-flow diagram called out and linked**, and links to the
docs and `user-inputs.csv`) and require **explicit approval of all four documents**.
**Echo the "how the model is solved" walkthrough and the full-path worked example in
the approval message itself** (condensed), and **show or link the process-flow
diagram** — this is the moment the user decides, so do not make them dig into the
docs to understand how their model will actually be computed. On approval:

```
python scripts/orchestrator.py set-stage --run-dir RUN --stage starting_documents_review
python scripts/orchestrator.py approve --run-dir RUN --type starting_documents \
    --artifact scope.md --artifact process-flow.md \
    --artifact data-requirements.md --artifact model-requirements.md
python scripts/orchestrator.py snapshot --run-dir RUN --label starting-documents \
    --artifact scope.md --artifact process-flow.md \
    --artifact data-requirements.md --artifact model-requirements.md
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
