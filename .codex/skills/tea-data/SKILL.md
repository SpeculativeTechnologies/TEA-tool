---
name: tea-data
description: Step 3 of the explicitly-invoked TEA orchestrator, running in sequence from tea-scope to tea-model to tea-data to tea-insights. Use when Codex needs to gather citation-backed TEA inputs and finalize the gap-free model inputs, then hand off to tea-insights to run the model.
---

# TEA Data Acquisition

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
- Treat research-first as invariant, not a mode: never offer estimation-led
  shortcuts, and estimate only residual blanks after the evidence pipeline.
- Use `python scripts/orchestrator.py` as the source of truth for state changes.
- Drive `workflow.md` through finalization to a gap-free `Main Input.csv`, record
  the `inputs_finalized` gate, then hand off to `tea-insights` (which runs the
  model and explores the results).
