---
name: tea-data
description: Step 3 of the explicitly-invoked TEA orchestrator, running in sequence from tea-scope to tea-model to tea-data. Use when Codex needs to gather citation-backed TEA inputs, populate the approved model, run it, and present real-data results.
---

# TEA Data Acquisition + Run

This is the Codex registration of the `tea-data` skill. Treat the shared
Claude-authored instructions as the source of truth for the full workflow and
load them before doing substantive work:

- `.claude/skills/tea-data/SKILL.md`
- `references/interaction-and-gates.md`
- `references/state-and-resume.md`
- `workflow.md`
- `.codex/agents/README.md`

## Core contract

- Invoke explicitly only. Do not self-trigger on general TEA questions.
- Gate-check for `model_approved` before beginning acquisition.
- Ask the user to choose Guided vs. Hands-off mode here, then lock it.
- Use `python scripts/orchestrator.py` as the source of truth for state changes.
- Drive `workflow.md` through finalization, then run the approved `model.py` on
  the finalized `Main Input.csv`.
- Re-approve only light inline `model.py` fixes; send structural changes back to
  `tea-model`.
