---
name: tea-scope
description: Step 1 of the explicitly-invoked TEA orchestrator, running in sequence from tea-scope to tea-model to tea-data. Use when Codex needs to start or resume TEA scoping from a rough idea and supplied materials, produce approved starting documents, and stop before model building.
---

# TEA Scoping

This is the Codex registration of the `tea-scope` skill. Treat the shared
Claude-authored instructions as the source of truth for the full workflow and
load them before doing substantive work:

- `.claude/skills/tea-scope/SKILL.md`
- `references/intake-and-compatibility.md`
- `references/state-and-resume.md`
- `references/interaction-and-gates.md`
- `.codex/agents/README.md`

## Core contract

- Invoke explicitly only. Do not self-trigger on general TEA questions.
- Keep schemas, files, stages, and CSV bookkeeping invisible to the user.
- Use plain language and ask one question at a time, with a recommended answer.
- Use `python scripts/orchestrator.py` as the source of truth for state changes.
- End at approval of `scope.md`, `data-requirements.md`, and
  `model-requirements.md`, then hand off to `tea-model`.
