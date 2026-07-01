---
name: tea-insights
description: Step 4 of the explicitly-invoked TEA orchestrator, running in sequence from tea-scope to tea-model to tea-data to tea-insights. Use when Codex needs to run the approved TEA model on the finalized inputs, present the real charts and results, and suggest new plots tied to the user's questions.
---

# TEA Insights

This is the Codex registration of the `tea-insights` skill. Treat the shared
Claude-authored instructions as the source of truth for the full workflow and
load them before doing substantive work:

- `.claude/skills/tea-insights/SKILL.md`
- `references/insights-and-iteration.md`
- `references/model-building.md`
- `references/state-and-resume.md`
- `.codex/agents/README.md`

## Core contract

- Invoke explicitly only. Do not self-trigger on general TEA questions.
- Gate-check for both `inputs_finalized` and `model_approved` before running.
- Use `python scripts/orchestrator.py` as the source of truth for state changes.
- Run the approved `model.py` on the finalized `Main Input.csv` to write the real
  `plots/` and `model-results.json`; present the charts, headline metrics, the
  workbook, and any benchmark validation.
- Surface the insights the real data shows, then propose ~3–6 new visualizations —
  each paired with the question about the user's idea it answers, tagged by cost
  (existing output / light model change / structural → back to `tea-model`).
- Leave it open-ended: accept suggestions, take new visualization requests, or make
  light `model.py`/`viz-spec.md` tweaks (re-`approve model_approved` after any edit);
  structural changes go back to `tea-model`. Set the stage to `complete` when the
  user is done; the run stays re-runnable.
