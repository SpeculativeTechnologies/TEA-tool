# TEA Data Acquisition (Codex / neutral entry point)

This is the Codex/OpenAI registration of the **tea-data** skill — Step 3 of the
four-skill TEA orchestrator, run in series (`/tea-scope` → `/tea-model` →
`/tea-data` → `/tea-insights`). Explicitly invoked only (see `agents/openai.yaml`:
`allow_implicit_invocation: false`) — never self-trigger on general TEA questions.

The full, platform-neutral instructions and references are shared with the Claude
Code layout and are the single source of truth. Load them from the repo root:

- **Skill body:** [`.claude/skills/tea-data/SKILL.md`](../../../.claude/skills/tea-data/SKILL.md)
- **References:**
  - [`references/interaction-and-gates.md`](../../../references/interaction-and-gates.md)
  - [`references/state-and-resume.md`](../../../references/state-and-resume.md)
  - [`workflow.md`](../../../workflow.md) (pipeline execution authority, Phases 1–7)
- **Specialist agents:** [`.codex/agents/README.md`](../../../.codex/agents/README.md)
  (Codex roster) — defined canonically in `.claude/agents/tea-*.md`.

## Operating contract (summary — read the shared SKILL.md for the rest)

- Step 3 of 4. Gather the real, citation-backed evidence and populate the inputs,
  then **finalize the gap-free input set and hand off to `/tea-insights`** (which
  runs the already-approved `model.py` to produce the charts and results).
- Gate-check first: require `model_approved` in `status.approvals.valid`, else send
  the user to `/tea-model`.
- This is the only skill that picks the execution mode: ask Guided vs. Hands-off,
  then `set-mode --lock`. It governs only the data-acquisition gates.
- Drive `workflow.md` Phases 1→7 to a gap-free `Main Input.csv`, finalize, and
  record the `inputs_finalized` gate (over `final/Main Input.csv`); `/tea-insights`
  then runs the model. Do **not** run the model or set `complete` here.
- The deterministic CLI `python scripts/orchestrator.py` is the source of truth.
