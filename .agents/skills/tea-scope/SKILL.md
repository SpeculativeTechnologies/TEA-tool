# TEA Scoping (Codex / neutral entry point)

This is the Codex/OpenAI registration of the **tea-scope** skill — Step 1 of the
three-skill TEA orchestrator, run in series (`/tea-scope` → `/tea-model` →
`/tea-data`). Explicitly invoked only (see `agents/openai.yaml`:
`allow_implicit_invocation: false`) — never self-trigger on general TEA questions.

The full, platform-neutral instructions and references are shared with the Claude
Code layout and are the single source of truth. Load them from the repo root:

- **Skill body:** [`.claude/skills/tea-scope/SKILL.md`](../../../.claude/skills/tea-scope/SKILL.md)
- **References:**
  - [`references/intake-and-compatibility.md`](../../../references/intake-and-compatibility.md)
  - [`references/state-and-resume.md`](../../../references/state-and-resume.md)
  - [`references/interaction-and-gates.md`](../../../references/interaction-and-gates.md)
- **Specialist agents:** [`.codex/agents/README.md`](../../../.codex/agents/README.md)
  (Codex roster) — defined canonically in `.claude/agents/tea-*.md`.

## Operating contract (summary — read the shared SKILL.md for the rest)

- Step 1 of 3. Take a non-expert from a rough idea plus supplied materials to three
  approved starting documents (`scope.md`, `data-requirements.md`,
  `model-requirements.md`), then hand off to `/tea-model`.
- Resolve ambiguity by **asking, not researching**: a relentless,
  one-question-at-a-time interview (~10–15 questions, each with a recommended
  answer) grounded in your own knowledge. Reading user-supplied files is fine;
  light web search only when genuinely stuck on a fact a question cannot resolve.
- Keep schemas, files, stages, and CSVs invisible. Plain language; you do the
  bookkeeping.
- The deterministic CLI `python scripts/orchestrator.py` is the source of truth.
  Do **not** pick an execution mode here — that happens in `/tea-data`.
- End at the `starting_documents` approval gate, then direct the user to
  `/tea-model`.
