---
name: tea-model
description: Step 2 of the explicitly-invoked TEA orchestrator, running in sequence from tea-scope to tea-model to tea-data to tea-insights. Use when Codex needs to turn approved TEA starting documents into a runnable model.py, dry-run it on dummy values, agree visualizations, and stop at model approval.
---

# TEA Modeling

This is the Codex registration of the `tea-model` skill. Treat the shared
Claude-authored instructions as the source of truth for the full workflow and
load them before doing substantive work:

- `.claude/skills/tea-model/SKILL.md`
- `references/model-building.md`
- `references/state-and-resume.md`
- `.codex/agents/README.md`

## Core contract

- Invoke explicitly only. Do not self-trigger on general TEA questions.
- Gate-check for approved starting documents before building anything.
- Use `python scripts/orchestrator.py` as the source of truth for state changes.
- Build a deterministic `model.py` that is a pure function of its `--inputs` CSV.
- Use rough dummy values from general knowledge only; do not web search for them.
- Write dry-run figures to `plots-dummy/` so the real run never overwrites them.
- End at `model_approved`, then hand off to `tea-data`.
