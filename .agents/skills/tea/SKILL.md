# TEA Orchestrator (Codex / neutral entry point)

This is the Codex/OpenAI registration of the **tea** skill (the TEA
orchestrator). The skill is **explicitly invoked only** (see `agents/openai.yaml`:
`allow_implicit_invocation: false`) — never self-trigger on general TEA questions.

The full, platform-neutral instructions and references are shared with the Claude
Code layout and are the single source of truth. Load them from the repo root:

- **Skill body:** [`.claude/skills/tea/SKILL.md`](../../../.claude/skills/tea/SKILL.md)
- **References:**
  - [`.claude/skills/tea/references/intake-and-compatibility.md`](../../../.claude/skills/tea/references/intake-and-compatibility.md)
  - [`.claude/skills/tea/references/interaction-and-gates.md`](../../../.claude/skills/tea/references/interaction-and-gates.md)
  - [`.claude/skills/tea/references/state-and-resume.md`](../../../.claude/skills/tea/references/state-and-resume.md)
- **Specialist agents:** [`.codex/agents/README.md`](../../../.codex/agents/README.md)
  (Codex roster) — defined canonically in `.claude/agents/tea-*.md`.

## Operating contract (summary — read the shared SKILL.md for the rest)

- You own the experience from a rough idea to finalized, citation-backed,
  model-ready TEA inputs. **V1 stops at populated inputs** — you never build,
  run, or visualize the model. You write `model-requirements.md` for a future V2.
- Keep schemas, files, stages, and CSVs invisible to the user. Plain language;
  you do the bookkeeping.
- The deterministic CLI `python scripts/orchestrator.py` is the source of truth
  for state, issues, approvals, snapshots, materials, and analyst inputs. Never
  hand-edit `orchestrator-state.json`, `issues.json`, or the user CSVs.
- Mandatory flow: init early → inventory materials → choose Guided/Hands-off mode
  → classify supplied values → compatibility + understanding check → write and
  get explicit approval of `scope.md`, `data-requirements.md`,
  `model-requirements.md` (both modes) → run `workflow.md` Phase 0→7 → finalize
  with no blank cells (one finite numeric value per cell, both modes).
- Subagents are read-only by default; you serialize all canonical writes.
