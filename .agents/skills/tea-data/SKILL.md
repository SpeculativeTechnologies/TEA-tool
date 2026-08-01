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
  then **finalize the gap-free input set and hand off to `/tea-insights`** by
  offering two ways to continue: **start a new thread/task and invoke
  `/tea-insights` there**, or type **`/clear`** and continue with `/tea-insights`.
  Emphasize that clearing or using a new thread keeps the tool performant.
- Gate-check first: require `model_approved` in `status.approvals.valid`, else send
  the user to `/tea-model`.
- When acquisition begins or resumes, explain the project's data-quality labels
  in plain language in the first response. Use the shared SKILL.md's
  A/B/C/D/E/U rubric, note that labels describe the evidence basis rather than
  guaranteed accuracy, and then ask for Guided vs. Hands-off mode if it is not
  already locked.
- This is the only skill that picks the execution mode: ask Guided vs. Hands-off,
  then `set-mode --lock`. It governs only the data-acquisition gates.
- Give a one-time warning with that choice that screened public sources are
  saved into the run folder. Hands-off authorizes noninteractive source
  downloads for the run; never use browser download popups or execute the files.
- Treat research-first as invariant, not a mode: run search/screen/extract for
  every option and estimate only residual Phase 6 blanks. Never offer a faster
  estimation-led path or materialize worker-generated values as user inputs.
- Drive `workflow.md` Phases 1→7 to a gap-free `Main Input.csv`, finalize, and
  record the `inputs_finalized` gate (over `final/Main Input.csv`); `/tea-insights`
  then runs the model in the new thread/task. Do **not** run the model or set
  `complete` here.
- The deterministic CLI `python scripts/orchestrator.py` is the source of truth.
