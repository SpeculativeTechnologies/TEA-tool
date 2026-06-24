# TEA Modeling (Codex / neutral entry point)

This is the Codex/OpenAI registration of the **tea-model** skill — Step 2 of the
three-skill TEA orchestrator, run in series (`/tea-scope` → `/tea-model` →
`/tea-data`). Explicitly invoked only (see `agents/openai.yaml`:
`allow_implicit_invocation: false`) — never self-trigger on general TEA questions.

The full, platform-neutral instructions and references are shared with the Claude
Code layout and are the single source of truth. Load them from the repo root:

- **Skill body:** [`.claude/skills/tea-model/SKILL.md`](../../../.claude/skills/tea-model/SKILL.md)
- **References:**
  - [`references/model-building.md`](../../../references/model-building.md)
  - [`references/state-and-resume.md`](../../../references/state-and-resume.md)
- **Specialist agents:** [`.codex/agents/README.md`](../../../.codex/agents/README.md)
  (Codex roster) — defined canonically in `.claude/agents/tea-*.md`.

## Operating contract (summary — read the shared SKILL.md for the rest)

- Step 2 of 3. Turn the approved `model-requirements.md` into a runnable
  `runs/<project>/model.py`, dry-run it on quick **dummy** values, agree the
  visualizations with the user, lock it behind the `model_approved` gate, then hand
  off to `/tea-data`.
- Gate-check first: require `starting_documents` in `status.approvals.valid`, else
  send the user to `/tea-scope`.
- `model.py` is a **pure function of its `--inputs` CSV** (reads `(entity,
  parameter)` values), writes one figure per chosen chart to `--outdir`, and emits
  a results JSON. No hard-coded numbers, no network, no randomness — so `/tea-data`
  re-runs the same file on real data.
- Dummy values are quick, rough, order-of-magnitude, from your own knowledge —
  **no web search**.
- Needs **matplotlib**. The deterministic CLI `python scripts/orchestrator.py` is
  the source of truth.
