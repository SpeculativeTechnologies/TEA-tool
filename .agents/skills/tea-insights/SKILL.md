# TEA Insights (Codex / neutral entry point)

This is the Codex/OpenAI registration of the **tea-insights** skill — Step 4 of the
four-skill TEA orchestrator, run in series (`/tea-scope` → `/tea-model` →
`/tea-data` → `/tea-insights`). Explicitly invoked only (see `agents/openai.yaml`:
`allow_implicit_invocation: false`) — never self-trigger on general TEA questions.

The full, platform-neutral instructions and references are shared with the Claude
Code layout and are the single source of truth. Load them from the repo root:

- **Skill body:** [`.claude/skills/tea-insights/SKILL.md`](../../../.claude/skills/tea-insights/SKILL.md)
- **References:**
  - [`references/insights-and-iteration.md`](../../../references/insights-and-iteration.md)
  - [`references/model-building.md`](../../../references/model-building.md)
  - [`references/state-and-resume.md`](../../../references/state-and-resume.md)
- **Specialist agents:** [`.codex/agents/README.md`](../../../.codex/agents/README.md)
  (Codex roster) — defined canonically in `.claude/agents/tea-*.md`.

## Operating contract (summary — read the shared SKILL.md for the rest)

- Step 4 of 4. Run the already-approved `model.py` on the finalized `Main Input.csv`
  to produce the **real** charts and results, then surface insights and propose new
  plots tied to the user's questions.
- Gate-check first: require both `inputs_finalized` (from `/tea-data`) and
  `model_approved` (from `/tea-model`) in `status.approvals.valid`, else send the
  user back to the skill that owns the missing gate.
- Run `model.py --inputs "<run>/Main Input.csv" --outdir "<run>/plots"
  --results "<run>/model-results.json"` then `export_workbook.py --run-dir <run>`.
  The real run writes `plots/` + `model-results.json`; the DUMMY figures from
  `/tea-model` stay in `plots-dummy/` (not overwritten).
- Propose ~3–6 new visualizations, each paired with the decision-relevant question
  it answers and tagged by cost (existing output / light model change / structural).
- Open-ended close: accept suggestions, take new visualization requests, or make
  light `model.py`/`viz-spec.md` tweaks (re-`approve model_approved` after any edit
  and log it); structural changes go back to `/tea-model`. Set the stage to
  `complete` when the user is done; the run stays re-runnable.
- Needs **matplotlib** (charts) and **openpyxl** (workbook). The deterministic CLI
  `python scripts/orchestrator.py` is the source of truth.
